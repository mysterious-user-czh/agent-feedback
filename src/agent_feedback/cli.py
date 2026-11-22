"""Command-line entry points for local use and Hermes import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .service import FeedbackService


def default_db() -> str:
    return os.environ.get("AGENT_FEEDBACK_DB", str(Path.home() / ".agent-feedback/feedback.db"))


def add_hermes_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("state_db", help="Hermes state.db path; opened read-only")
    parser.add_argument("--hours", type=int, help="Only import sessions active in the last N hours")
    parser.add_argument("--include-subagents", action="store_true",
                        help="Also import delegated child sessions (excluded by default)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-feedback", description="Local-first agent feedback tools")
    parser.add_argument("--db", default=default_db(), help="Feedback SQLite path")
    parser.add_argument("--contracts", help="JSON file containing deterministic skill contracts")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="Generate a feedback report")
    report.add_argument("--agent")
    report.add_argument("--selection")
    report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    report.add_argument("--review-status", choices=["all", "pending", "reviewed"], default="all")
    report.add_argument("--priority", choices=["P0", "P1", "P2", "none"])
    report.add_argument("--execution", choices=["pass", "fail", "unknown"])
    report.add_argument("--has-tool-errors", action=argparse.BooleanOptionalAction, default=None)
    report.add_argument("--has-observed-label", action=argparse.BooleanOptionalAction, default=None)
    report.add_argument("--sort", choices=["priority", "source_time", "tool_errors"], default="priority")
    report.add_argument("--limit", type=int, default=20)
    report.add_argument("--offset", type=int, default=0)
    imp = sub.add_parser("import-hermes", help="Read-only import from a Hermes state.db")
    add_hermes_source_arguments(imp)
    collect = sub.add_parser("collect-hermes", help="Import once and require complete source-to-store coverage")
    add_hermes_source_arguments(collect)
    collect.add_argument("--status-path", help="Atomic collector status JSON path")
    watch = sub.add_parser("watch-hermes", help="Continuously import Hermes evidence with coverage checks")
    add_hermes_source_arguments(watch)
    watch.add_argument("--interval", type=int, default=60, help="Seconds between collections; minimum 5")
    watch.add_argument("--cycles", type=int, default=0, help="Stop after N cycles; 0 means run until stopped")
    watch.add_argument("--status-path", help="Atomic collector status JSON path")
    isolated = sub.add_parser("import-isolated", help="Import isolated run records and independent oracle evidence")
    isolated.add_argument("batch_dir", help="Batch containing results.json and raw/<run_id>.json")
    isolated.add_argument("spec", help="Frozen task specification JSON")
    session = sub.add_parser("import-session", help="Import an engine-neutral skill-up SessionResult")
    session.add_argument("result", help="SessionResult JSON")
    session.add_argument("--goal", help="Goal override; otherwise use the first user transcript message")
    session.add_argument("--external-id", help="Stable idempotency key")
    session.add_argument("--verification", help="JSON object containing independent verification evidence")
    track = sub.add_parser("track-skillup", help="Log a sanitized skill-up result to local MLflow")
    track.add_argument("result", help="skill-up result.json")
    track.add_argument("--tracking-uri", required=True, help="Local file: MLflow tracking URI")
    track.add_argument("--experiment", default="agent-feedback")
    track.add_argument("--artifact-root", required=True, help="Local artifact directory")
    track.add_argument("--code-version", required=True)
    track.add_argument("--metadata", help="JSON object with candidate/config/skill-tree/fixture/model versions")
    args = parser.parse_args()
    if args.command == "track-skillup":
        from .tracking import log_skillup_result
        metadata = json.loads(args.metadata) if args.metadata else None
        print(json.dumps(log_skillup_result(args.result, tracking_uri=args.tracking_uri,
                                            experiment_name=args.experiment, artifact_root=args.artifact_root,
                                            code_version=args.code_version, metadata=metadata), ensure_ascii=False, indent=2))
        return
    if args.command in {"collect-hermes", "watch-hermes"}:
        from .auto_collect import collect_once, watch_hermes
        if args.command == "collect-hermes":
            status = collect_once(args.state_db, args.db, args.contracts, args.hours,
                                  args.include_subagents, args.status_path)
            print(json.dumps(status, ensure_ascii=False, indent=2))
            if not status["success"]:
                raise SystemExit(2)
        else:
            watch_hermes(args.state_db, args.db, args.contracts, args.hours,
                         args.include_subagents, args.interval, args.cycles, args.status_path)
        return
    service = FeedbackService(args.db, args.contracts)
    try:
        if args.command == "report":
            print(service.report(agent=args.agent, selection=args.selection,
                                 review_status=args.review_status, limit=args.limit, offset=args.offset,
                                 response_format=args.format, priority=args.priority,
                                 execution=args.execution, has_tool_errors=args.has_tool_errors,
                                 has_observed_label=args.has_observed_label, sort=args.sort))
        elif args.command == "import-hermes":
            from .adapters.hermes import import_hermes
            print(json.dumps(import_hermes(args.state_db, service, args.hours, args.include_subagents), ensure_ascii=False, indent=2))
        elif args.command == "import-isolated":
            from .adapters.isolated_hermes import import_isolated_batch
            print(json.dumps(import_isolated_batch(args.batch_dir, args.spec, service), ensure_ascii=False, indent=2))
        elif args.command == "import-session":
            from .adapters.session_result import import_session_result
            verification = json.loads(args.verification) if args.verification else None
            print(json.dumps(import_session_result(args.result, service, verification=verification,
                                                   goal=args.goal, external_id=args.external_id), ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
