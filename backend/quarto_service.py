import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from report_service import (
    compute_content_hash,
    read_qmd,
    report_logs_dir,
    report_output_dir,
    report_qmd_path,
)

RENDER_TIMEOUT_SECONDS = int(os.getenv("RENDER_TIMEOUT_SECONDS", "180"))


def build_quarto_command(
    report_id: int,
    fmt: str,
    params: Dict[str, Any],
) -> List[str]:
    input_path = report_qmd_path(report_id)
    output_dir = report_output_dir(report_id)
    cmd = [
        "quarto",
        "render",
        str(input_path),
        "--to",
        fmt,
        "--output-dir",
        str(output_dir),
    ]
    for key, value in params.items():
        cmd.extend(["-P", f"{key}:{value}"])
    return cmd


def _guess_output_path(report_id: int, fmt: str) -> Optional[str]:
    qmd_file = report_qmd_path(report_id)
    output = report_output_dir(report_id)
    stem = qmd_file.stem
    expected = output / f"{stem}.{fmt}"
    if expected.exists():
        return str(expected)
    matches = list(output.glob(f"*.{fmt}"))
    if matches:
        return str(matches[0])
    return None


def run_render_job(report_id: int, job_id: int, params: Dict[str, Any], formats: List[str]) -> Tuple[bool, Dict[str, Any], str, Optional[str]]:
    logs_dir = report_logs_dir(report_id)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"render_{job_id}.log"

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"

    output_paths: Dict[str, str] = {}
    errors: List[str] = []

    qmd_text = read_qmd(report_id)
    qmd_hash = compute_content_hash(qmd_text)

    with log_path.open("w", encoding="utf-8") as log:
        for fmt in formats:
            cmd = build_quarto_command(report_id, fmt, params)
            log.write(f"$ {' '.join(cmd)}\n")
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=log,
                    stderr=log,
                    timeout=RENDER_TIMEOUT_SECONDS,
                    check=False,
                    env=env,
                    cwd=str(report_qmd_path(report_id).parent),
                )
                if proc.returncode != 0:
                    errors.append(f"Render failed for format={fmt} with exit code {proc.returncode}")
                else:
                    out = _guess_output_path(report_id, fmt)
                    if out:
                        output_paths[fmt] = out
                    else:
                        errors.append(f"Render completed for format={fmt} but output file was not found")
            except subprocess.TimeoutExpired:
                errors.append(f"Render timeout for format={fmt} after {RENDER_TIMEOUT_SECONDS}s")

    manifest = {
        "report_id": report_id,
        "job_id": job_id,
        "qmd_hash": qmd_hash,
        "params": params,
        "formats": formats,
        "quarto_version": _quarto_version(),
        "python_version": _python_version(),
        "created_at": _utc_now(),
        "output_paths": output_paths,
        "log_path": str(log_path),
    }

    if errors:
        return False, manifest, str(log_path), " | ".join(errors)
    return True, manifest, str(log_path), None


def _quarto_version() -> str:
    try:
        proc = subprocess.run(["quarto", "--version"], capture_output=True, text=True, timeout=15, check=False)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except OSError:
        pass
    return "unknown"


def _python_version() -> str:
    return sys.version.split(" ")[0]


def _utc_now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"


def parse_job_payload(job_row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    params = json.loads(job_row.get("params_json") or "{}")
    formats = json.loads(job_row.get("output_formats") or "[\"html\"]")
    return params, formats
