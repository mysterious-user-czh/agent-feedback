"""Loopback-only human review API and static site server.

The API deliberately exposes only the existing FeedbackService operations. It is
not an Internet server: there is no authentication, CORS, or remote write support.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .service import FeedbackService

MAX_BODY = 64 * 1024
DECISIONS = {"confirm", "false_positive", "insufficient"}
FAILURE_STAGES = {"routing", "execution", "environment", "requirements"}


def progress(service: FeedbackService) -> dict[str, int]:
    total = service.store.one("SELECT COUNT(*) AS n FROM tasks")["n"]
    reviewed = service.store.one("SELECT COUNT(*) AS n FROM labels WHERE source='human'")["n"]
    return {"total": total, "reviewed": reviewed, "pending": total - reviewed}


def find_task(service: FeedbackService, task_id: str) -> dict[str, Any] | None:
    if not service.store.one("SELECT task_id FROM tasks WHERE task_id=?", (task_id,)):
        return None
    offset = 0
    while True:
        result = json.loads(service.report(limit=100, offset=offset, response_format="json"))
        for item in result["items"]:
            if item["task_id"] == task_id:
                return item
        if not result["has_more"]:
            return None
        offset = result["next_offset"]


def task_detail(service: FeedbackService, task_id: str) -> dict[str, Any] | None:
    item = find_task(service, task_id)
    if item is None:
        return None
    events = [service.store.payload(row) for row in service.store.all(
        "SELECT rowid AS sequence,* FROM events WHERE task_id=? ORDER BY rowid", (task_id,),
    )]
    revisions = service.store.all(
        "SELECT * FROM label_revisions WHERE task_id=? ORDER BY rowid DESC", (task_id,),
    )
    return {"task": item, "events": events, "revisions": revisions}


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], service: FeedbackService,
                 static_dir: str | Path, *, demo: bool = False):
        self.service = service
        self.static_dir = Path(static_dir).resolve()
        self.demo = demo
        super().__init__(address, ReviewHandler)


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("AGENT_FEEDBACK_HTTP_LOG"):
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _local_write_allowed(self) -> bool:
        if self.headers.get("X-Agent-Feedback-Local") != "1":
            return False
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in {"same-origin", "none"}:
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != self.headers.get("Host"):
                return False
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json(200, {"status": "ok", "version": __version__, "demo": self.server.demo,
                                 "writable": True, "scope": "loopback"})
                return
            if parsed.path == "/api/tasks":
                self._tasks(parse_qs(parsed.query))
                return
            if parsed.path == "/api/task":
                task_id = parse_qs(parsed.query).get("id", [""])[0]
                detail = task_detail(self.server.service, task_id) if task_id else None
                if detail is None:
                    self._error(404, "任务不存在")
                else:
                    self._json(200, detail)
                return
            if parsed.path.startswith("/api/"):
                self._error(404, "接口不存在")
                return
            self._static(parsed.path)
        except (ValueError, TypeError) as exc:
            self._error(400, str(exc))
        except Exception:
            self._error(500, "本地服务处理失败，请查看服务日志")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        # One write per connection also prevents an unread rejected body from
        # being parsed as a second HTTP request on persistent connections.
        self.close_connection = True
        try:
            if urlparse(self.path).path != "/api/label":
                self._error(404, "接口不存在")
                return
            if not self._local_write_allowed():
                self._error(403, "仅允许同源本机审核请求")
                return
            if self.headers.get_content_type() != "application/json":
                self._error(415, "请求必须是 application/json")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY:
                self._error(413, "请求为空或超过 64 KB")
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("请求必须是 JSON 对象")
            result = self._label(data)
            status = 200 if result.get("saved") or result.get("duplicate") else 409
            self._json(status, {"result": result, "progress": progress(self.server.service)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))
        except Exception:
            self._error(500, "保存失败，请查看服务日志")

    def _tasks(self, query: dict[str, list[str]]) -> None:
        def one(name: str, default: Any = None) -> Any:
            values = query.get(name)
            return values[-1] if values else default

        limit = int(one("limit", 100))
        offset = int(one("offset", 0))
        result = json.loads(self.server.service.report(
            review_status=one("review_status", "all"), priority=one("priority"),
            execution=one("execution"), sort=one("sort", "priority"),
            search=one("q"), limit=limit, offset=offset, response_format="json",
        ))
        result["progress"] = progress(self.server.service)
        self._json(200, result)

    def _label(self, data: dict[str, Any]) -> dict[str, Any]:
        task_id = data.get("task_id")
        decision = data.get("decision")
        comment = data.get("comment")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必填")
        if decision not in DECISIONS:
            raise ValueError("decision 必须是 confirm、false_positive 或 insufficient")
        if not isinstance(comment, str) or not 2 <= len(comment.strip()) <= 1800:
            raise ValueError("审核说明须为 2–1800 个字符")
        comment = comment.strip()
        if decision == "confirm":
            stage = data.get("failure_stage")
            if stage not in FAILURE_STAGES:
                raise ValueError("确认问题时必须选择有效失败阶段")
            outcome = "failure"
            text = f"审核结论：确认问题\n{comment}"
        else:
            stage = "unknown"
            outcome = "unknown"
            title = "误报" if decision == "false_positive" else "证据不足"
            text = f"审核结论：{title}\n{comment}"
        return self.server.service.label(
            task_id, outcome=outcome, failure_stage=stage, comment=text,
            source="human", actor="local-review", reason=comment,
        )

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        # Serve only public UI assets, never the co-located demo database,
        # launcher source, hidden files, or future files added under app/data.
        public_files = {"index.html", "styles.css", "favicon.svg", "src/main.js"}
        if relative.replace("\\", "/") not in public_files:
            self._error(404, "页面不存在")
            return
        candidate = (self.server.static_dir / relative).resolve()
        try:
            candidate.relative_to(self.server.static_dir)
        except ValueError:
            self._error(403, "禁止访问该路径")
            return
        if not candidate.is_file():
            self._error(404, "页面不存在")
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local human review website")
    parser.add_argument("--db", required=True, help="Feedback database; use an isolated demo DB for evaluation")
    parser.add_argument("--contracts", help="Skill contracts JSON")
    parser.add_argument("--static-dir", required=True, help="Directory containing index.html")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7100)
    parser.add_argument("--demo", action="store_true", help="Mark the UI as using demonstration data")
    args = parser.parse_args()
    service = FeedbackService(args.db, args.contracts)
    server = ReviewServer((args.host, args.port), service, args.static_dir, demo=args.demo)
    try:
        print(f"Agent Feedback review: http://{args.host}:{server.server_port}/", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        service.close()


if __name__ == "__main__":
    main()
