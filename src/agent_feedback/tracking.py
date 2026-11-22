"""Optional MLflow logging for sanitized skill-up results; never a core dependency."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@contextmanager
def _local_file_store_enabled():
    """Opt in only for this process operation; MLflow 3.18+ otherwise rejects file stores."""
    previous = os.environ.get("MLFLOW_ALLOW_FILE_STORE")
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MLFLOW_ALLOW_FILE_STORE", None)
        else:
            os.environ["MLFLOW_ALLOW_FILE_STORE"] = previous


def sanitize_skillup_result(payload: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for case in payload.get("case_results") or []:
        checks = []
        grading = case.get("grading") or {}
        for assertion in grading.get("assertion_results") or []:
            item = {"kind": "script" if assertion.get("text", "").startswith("script:") else "expect",
                    "passed": bool(assertion.get("passed"))}
            evidence = assertion.get("evidence")
            if item["kind"] == "script" and isinstance(evidence, str):
                try:
                    decoded = json.loads(evidence)
                    if isinstance(decoded, dict) and all(isinstance(v, bool) for v in decoded.values()):
                        item["checks"] = decoded
                except json.JSONDecodeError:
                    pass
            checks.append(item)
        cases.append({"case_id": case.get("case_id"), "status": case.get("status"),
                      "duration_ms": case.get("duration_ms"), "turns": case.get("turns"),
                      "checks": checks})
    return {"schema_version": payload.get("schema_version"), "engine": payload.get("engine_name"),
            "observed_model": (payload.get("observed_configuration") or {}).get("model") or "unknown",
            "start_time": payload.get("start_time"), "end_time": payload.get("end_time"),
            "cases": cases, "token_metrics": "unknown_not_reported"}


def _tracking_context(tracking_uri: str, artifact_root: str | Path):
    parsed_uri = urlparse(tracking_uri)
    if parsed_uri.scheme != "file" or parsed_uri.netloc not in {"", "localhost"}:
        raise ValueError("Only a local file: MLflow tracking URI is allowed by this integration")
    artifact_uri = Path(artifact_root).resolve().as_uri()
    if urlparse(artifact_uri).netloc not in {"", "localhost"}:
        raise ValueError("MLflow artifact root must be a local directory")
    return artifact_uri


def _version(metadata: dict[str, Any] | None) -> dict[str, str]:
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    allowed = ("candidate", "config_hash", "skill_tree_hash", "fixture_hash", "case_source",
               "model_version", "case_id", "arm", "parent_run_id", "source_case_hash", "oracle_hash")
    return {key: str((metadata or {}).get(key) or "unknown") for key in allowed}


def log_skillup_result(result_path: str | Path, *, tracking_uri: str, experiment_name: str,
                       artifact_root: str | Path, code_version: str,
                       metadata: dict[str, Any] | None = None) -> dict[str, str]:
    artifact_uri = _tracking_context(tracking_uri, artifact_root)
    path = Path(result_path).resolve()
    raw = path.read_bytes()
    payload = json.loads(raw)
    clean = sanitize_skillup_result(payload)
    source_hash = hashlib.sha256(raw).hexdigest()
    version = _version(metadata)
    clean["version"] = version
    try:
        with _local_file_store_enabled():
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                mlflow.create_experiment(experiment_name, artifact_location=artifact_uri)
            mlflow.set_experiment(experiment_name)
            nested = version["parent_run_id"] != "unknown"
            run_name = f"skillup-{version['arm']}-{source_hash[:12]}" if nested else "skillup-" + source_hash[:12]
            with mlflow.start_run(run_name=run_name, nested=nested) as run:
                mlflow.log_params({"engine": clean["engine"] or "unknown", "model": clean["observed_model"],
                                   "source_sha256": source_hash, "code_version": code_version,
                                   "event_contract": "v1", "skillup_version": "0.16.0", **version})
                cases = clean["cases"]
                mlflow.log_metrics({"cases": len(cases),
                                    "passed": sum(c["status"] == "PASS" for c in cases),
                                    "failed": sum(c["status"] == "FAIL" for c in cases),
                                    "errors": sum(c["status"] == "ERROR" for c in cases),
                                    "duration_ms": sum(c.get("duration_ms") or 0 for c in cases),
                                    "turns": sum(c.get("turns") or 0 for c in cases)})
                mlflow.set_tags({"privacy": "sanitized_no_prompt_response_transcript",
                                 "token_metrics": "unknown_not_reported"})
                mlflow.log_dict(clean, "sanitized-result.json")
                return {"run_id": run.info.run_id, "experiment_id": run.info.experiment_id,
                        "source_sha256": source_hash}
    except ImportError as exc:
        raise RuntimeError("Install the optional 'mlflow' dependency in the project environment") from exc


def log_skillup_case(result_runs: list[dict[str, Any]], *, tracking_uri: str, experiment_name: str,
                     artifact_root: str | Path, code_version: str,
                     metadata: dict[str, Any]) -> dict[str, Any]:
    """Log one sanitized parent case and real nested before/after/control child runs."""
    if not isinstance(result_runs, list) or not result_runs:
        raise ValueError("result_runs must be a non-empty list")
    version = _version(metadata)
    if version["case_id"] == "unknown":
        raise ValueError("case metadata requires case_id")
    artifact_uri = _tracking_context(tracking_uri, artifact_root)
    try:
        with _local_file_store_enabled():
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                mlflow.create_experiment(experiment_name, artifact_location=artifact_uri)
            mlflow.set_experiment(experiment_name)
            with mlflow.start_run(run_name="case-" + version["case_id"]) as parent:
                parent_params = {key: value for key, value in version.items() if key not in {"arm", "parent_run_id"}}
                mlflow.log_params({"code_version": code_version, "event_contract": "v1",
                                   "skillup_version": "0.16.0", **parent_params})
                mlflow.set_tags({"privacy": "sanitized_no_prompt_response_transcript_session_id",
                                 "role": "regression_case_parent"})
                children = []
                for spec in result_runs:
                    if not isinstance(spec, dict) or not isinstance(spec.get("arm"), str):
                        raise ValueError("each result run requires an arm and result_path")
                    child_metadata = dict(metadata) | dict(spec.get("metadata") or {}) | {
                        "arm": spec["arm"], "parent_run_id": parent.info.run_id,
                    }
                    info = log_skillup_result(
                        spec["result_path"], tracking_uri=tracking_uri, experiment_name=experiment_name,
                        artifact_root=artifact_root, code_version=code_version, metadata=child_metadata,
                    )
                    children.append(info | {"arm": spec["arm"]})
                mlflow.log_metrics({"child_runs": len(children),
                                    "before_runs": sum(child["arm"] == "before" for child in children),
                                    "after_runs": sum(child["arm"] == "after" for child in children),
                                    "control_runs": sum(child["arm"] == "control" for child in children)})
                return {"parent_run_id": parent.info.run_id, "experiment_id": parent.info.experiment_id,
                        "children": children}
    except ImportError as exc:
        raise RuntimeError("Install the optional 'mlflow' dependency in the project environment") from exc
