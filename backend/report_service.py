import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_ROOT", "data/artifacts"))


def _safe_int_id(value: int) -> str:
    return str(int(value))


def report_workspace(report_id: int) -> Path:
    safe_id = _safe_int_id(report_id)
    path = ARTIFACT_ROOT / "reports" / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_qmd_path(report_id: int) -> Path:
    return report_workspace(report_id) / "report.qmd"


def report_output_dir(report_id: int) -> Path:
    output = report_workspace(report_id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


def report_logs_dir(report_id: int) -> Path:
    logs = report_workspace(report_id) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def report_manifest_path(report_id: int) -> Path:
    return report_workspace(report_id) / "manifest.json"


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def default_qmd_skeleton(title: str) -> str:
    safe_title = title.replace('"', "'")
    return f"""---
title: \"{safe_title}\"
format:
  html: default
params:
  objective_id: null
  persona_id: null
  dataset_refs: []
---

# Summary

Write your report here.
"""


def write_qmd(report_id: int, qmd_text: str) -> str:
    qmd_path = report_qmd_path(report_id)
    qmd_path.parent.mkdir(parents=True, exist_ok=True)
    qmd_path.write_text(qmd_text, encoding="utf-8")
    return str(qmd_path)


def read_qmd(report_id: int) -> str:
    qmd_path = report_qmd_path(report_id)
    if not qmd_path.exists():
        return ""
    return qmd_path.read_text(encoding="utf-8")


def read_manifest(report_id: int) -> Optional[Dict[str, Any]]:
    manifest_path = report_manifest_path(report_id)
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_manifest(report_id: int, payload: Dict[str, Any]) -> str:
    manifest_path = report_manifest_path(report_id)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(manifest_path)


def manifest_cache_hit(
    report_id: int,
    content_hash: str,
    params: Dict[str, Any],
    formats: List[str],
) -> bool:
    manifest = read_manifest(report_id)
    if not manifest:
        return False
    if manifest.get("qmd_hash") != content_hash:
        return False
    if manifest.get("params") != params:
        return False
    if sorted(manifest.get("formats", [])) != sorted(formats):
        return False
    output_paths = manifest.get("output_paths", {})
    for fmt in formats:
        candidate = output_paths.get(fmt)
        if not candidate:
            return False
        if not Path(candidate).exists():
            return False
    return True


def read_log_tail(log_path: Optional[str], lines: int = 200) -> str:
    if not log_path:
        return ""
    candidate = Path(log_path)
    if not candidate.exists() or not candidate.is_file():
        return ""

    content = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"
