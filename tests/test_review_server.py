import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from agent_feedback.review_server import ReviewServer
from agent_feedback.service import FeedbackService
from examples.review_demo import create_demo


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT.parent / "app"
CONTRACTS = ROOT / "examples" / "contracts.json"


class ReviewServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        create_demo(self.root / "review.db", CONTRACTS)
        self.service = FeedbackService(self.root / "review.db", CONTRACTS)
        self.server = ReviewServer(("127.0.0.1", 0), self.service, APP, demo=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        items = self.request("GET", "/api/tasks")[1]["items"]
        self.ids = {item["external_id"]: item["task_id"] for item in items}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.service.close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        data = json.loads(raw) if content_type.startswith("application/json") else raw.decode("utf-8")
        status = response.status
        connection.close()
        return status, data

    def write_headers(self, origin=None):
        return {"X-Agent-Feedback-Local": "1",
                "Origin": origin or f"http://127.0.0.1:{self.port}"}

    def test_health_static_and_security_headers(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["demo"])
        self.assertEqual(health["scope"], "loopback")
        self.assertNotIn("db", health)
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Agent Skills Feedback", page)
        status, _ = self.request("GET", "/../pyproject.toml")
        self.assertIn(status, {403, 404})
        status, missing = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", missing)

    def test_queue_progress_priorities_and_detail(self):
        status, report = self.request("GET", "/api/tasks?review_status=all&limit=100")
        self.assertEqual(status, 200)
        self.assertEqual(report["progress"], {"total": 5, "reviewed": 2, "pending": 3})
        priorities = {item["external_id"]: item["priority"] for item in report["items"]}
        self.assertEqual(priorities, {"demo-1": "P0", "demo-2": "P1", "demo-3": "P1",
                                      "demo-4": "P2", "demo-5": None})
        _, pending = self.request("GET", "/api/tasks?review_status=pending&priority=P1")
        self.assertEqual(pending["filtered_total"], 2)
        self.assertEqual(pending["progress"]["total"], 5)
        status, detail = self.request("GET", f"/api/task?id={self.ids['demo-1']}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["task"]["task_id"], self.ids["demo-1"])
        self.assertGreaterEqual(len(detail["events"]), 4)
        self.assertEqual(len(detail["revisions"]), 1)
        status, _ = self.request("GET", "/api/task?id=missing")
        self.assertEqual(status, 404)

    def test_full_dataset_search_and_static_allowlist(self):
        for query, expected_ids in (
            ("PDF", {"demo-5"}),
            ("docx-editing", {"demo-1", "demo-2", "demo-3", "demo-4"}),
            (self.ids["demo-3"], {"demo-3"}),
        ):
            status, result = self.request("GET", f"/api/tasks?review_status=all&q={query}")
            self.assertEqual(status, 200)
            self.assertEqual({item["external_id"] for item in result["items"]}, expected_ids)
            self.assertEqual(result["total"], len(expected_ids))
            self.assertEqual(result["progress"], {"total": 5, "reviewed": 2, "pending": 3})
        status, _ = self.request("GET", "/api/tasks?q=" + "x" * 201)
        self.assertEqual(status, 400)
        for path in ("/data/review-demo.db", "/server.mjs", "/package.json", "/.gitignore"):
            status, _ = self.request("GET", path)
            self.assertEqual(status, 404)

    def test_confirm_failure_writes_human_revision_and_progress(self):
        task_id = self.ids["demo-2"]
        payload = {"task_id": task_id, "decision": "confirm", "failure_stage": "execution",
                   "comment": "已核对原始回复，任务目标被错误执行。"}
        status, saved = self.request("POST", "/api/label", payload, self.write_headers())
        self.assertEqual(status, 200)
        self.assertTrue(saved["result"]["saved"])
        self.assertEqual(saved["progress"], {"total": 5, "reviewed": 3, "pending": 2})
        label = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (task_id,))
        self.assertEqual(label["source"], "human")
        self.assertEqual(label["outcome"], "failure")
        self.assertEqual(label["failure_stage"], "execution")
        self.assertTrue(label["comment"].startswith("审核结论：确认问题"))
        revisions = self.service.store.all("SELECT * FROM label_revisions WHERE task_id=?", (task_id,))
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[-1]["reason"], payload["comment"])
        status, duplicate = self.request("POST", "/api/label", payload, self.write_headers())
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["result"]["duplicate"])
        self.assertEqual(self.service.store.one(
            "SELECT COUNT(*) AS n FROM label_revisions WHERE task_id=?", (task_id,))["n"], 2)

    def test_false_positive_revises_without_claiming_success(self):
        task_id = self.ids["demo-1"]
        before = self.service.store.one("SELECT COUNT(*) AS n FROM label_revisions WHERE task_id=?", (task_id,))["n"]
        status, saved = self.request("POST", "/api/label", {
            "task_id": task_id, "decision": "false_positive", "comment": "复核后该信号不符合问题定义。",
        }, self.write_headers())
        self.assertEqual(status, 200)
        label = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (task_id,))
        self.assertEqual(label["outcome"], "unknown")
        self.assertEqual(label["failure_stage"], "unknown")
        self.assertTrue(label["comment"].startswith("审核结论：误报"))
        revisions = self.service.store.all("SELECT * FROM label_revisions WHERE task_id=? ORDER BY rowid", (task_id,))
        self.assertEqual(len(revisions), before + 1)
        self.assertEqual(revisions[-1]["reason"], "复核后该信号不符合问题定义。")

    def test_insufficient_evidence_counts_as_reviewed(self):
        task_id = self.ids["demo-4"]
        status, saved = self.request("POST", "/api/label", {
            "task_id": task_id, "decision": "insufficient", "comment": "缺少原始会话，无法判断是否重复调用。",
        }, self.write_headers())
        self.assertEqual(status, 200)
        self.assertEqual(saved["progress"]["reviewed"], 3)
        label = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (task_id,))
        self.assertEqual(label["outcome"], "unknown")
        self.assertTrue(label["comment"].startswith("审核结论：证据不足"))

    def test_rejects_cross_site_invalid_and_oversized_writes(self):
        payload = {"task_id": self.ids["demo-2"], "decision": "confirm",
                   "failure_stage": "routing", "comment": "有效说明"}
        status, _ = self.request("POST", "/api/label", payload)
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/label", payload,
                                 self.write_headers("https://attacker.invalid"))
        self.assertEqual(status, 403)
        for change in ({"decision": "bad"}, {"failure_stage": "unknown"}, {"comment": "x"}):
            status, _ = self.request("POST", "/api/label", {**payload, **change}, self.write_headers())
            self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/label", {**payload, "task_id": "missing"}, self.write_headers())
        self.assertEqual(status, 400)
        try:
            status, _ = self.request("POST", "/api/label", {**payload, "comment": "x" * 65536}, self.write_headers())
            self.assertEqual(status, 413)
        except ConnectionAbortedError:
            # Windows may reset a connection closed with an unread oversized body.
            # That is also a rejection; the server must remain healthy and unchanged.
            pass
        status, health = self.request("GET", "/api/health")
        self.assertEqual((status, health["status"]), (200, "ok"))
        unchanged = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (self.ids["demo-2"],))
        self.assertEqual(unchanged["source"], "observed")
        self.assertNotIn("审核结论：确认问题", unchanged["comment"])

    def test_pagination_and_filter_validation(self):
        status, page = self.request("GET", "/api/tasks?limit=2&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(page["count"], 2)
        self.assertTrue(page["has_more"])
        status, _ = self.request("GET", "/api/tasks?limit=101")
        self.assertEqual(status, 400)
        status, _ = self.request("GET", "/api/tasks?review_status=bad")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
