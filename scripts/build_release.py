"""Build the Python wheel and self-contained Hermes Windows review package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
DIST = ROOT / "dist"
STAGING = ROOT / "build" / f"hermes-agent-feedback-plugin-v{VERSION}"
PACKAGE = DIST / f"hermes-agent-feedback-plugin-v{VERSION}.zip"


def copy_file(source: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / source, target)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "--wheel-dir", str(DIST),
    ], cwd=ROOT, check=True)
    wheel = DIST / f"agent_feedback_local-{VERSION}-py3-none-any.whl"
    if not wheel.is_file():
        raise RuntimeError(f"Expected wheel was not built: {wheel}")
    if STAGING.exists():
        shutil.rmtree(STAGING)
    payload = STAGING / "payload"
    payload.mkdir(parents=True)
    shutil.copy2(wheel, payload / wheel.name)
    for name in ("contracts.json",):
        copy_file(f"examples/{name}", payload / name)
    shutil.copytree(ROOT / "skill" / "agent-feedback", payload / "skill" / "agent-feedback")
    shutil.copytree(
        ROOT / "review-ui", payload / "review-ui",
        ignore=shutil.ignore_patterns("data", "node_modules", "__pycache__"),
    )
    plugin = ROOT / "packaging" / "hermes-plugin"
    for source in plugin.iterdir():
        if source.is_file():
            shutil.copy2(source, STAGING / source.name)
    for name in ("Start Agent Skills Feedback.cmd", "Stop Agent Skills Feedback.cmd"):
        copy_file(name, STAGING / name)
    shutil.copytree(ROOT / "scripts", STAGING / "scripts", ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    PACKAGE.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(PACKAGE, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(STAGING.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(STAGING))
    with zipfile.ZipFile(PACKAGE) as archive:
        names = archive.namelist()
        assert not any(name.endswith((".db", ".db-wal", ".db-shm")) for name in names)
        for required in (
            "install.ps1", "Start Agent Skills Feedback.cmd", "Stop Agent Skills Feedback.cmd",
            "scripts/start-review.ps1", "scripts/stop-review.ps1", "payload/review-ui/index.html",
            f"payload/{wheel.name}",
        ):
            assert required in names, required
    outputs = []
    for path in (wheel, PACKAGE):
        outputs.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    print(json.dumps({"version": VERSION, "files": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
