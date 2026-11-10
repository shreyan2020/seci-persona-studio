import os
import time
import uuid

from database import db
from quarto_service import parse_job_payload, run_render_job
from report_service import write_manifest

POLL_INTERVAL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "2"))
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")


def _update_success(report_id: int, job_id: int, manifest_path: str, manifest: dict, log_path: str):
    db.update_render_job_result(job_id=job_id, status="success", log_path=log_path)
    db.update_report_render_result(
        report_id=report_id,
        html_path=manifest.get("output_paths", {}).get("html"),
        pdf_path=manifest.get("output_paths", {}).get("pdf"),
        manifest_path=manifest_path,
        log_path=log_path,
        status="success",
        error_message=None,
    )


def _update_failure(report_id: int, job_id: int, log_path: str, error_message: str):
    db.update_render_job_result(job_id=job_id, status="failed", log_path=log_path, error_message=error_message)
    db.update_report_render_result(
        report_id=report_id,
        html_path=None,
        pdf_path=None,
        manifest_path="",
        log_path=log_path,
        status="failed",
        error_message=error_message,
    )


def run_worker_forever():
    print(f"Starting render worker {WORKER_ID}")
    while True:
        try:
            job = db.claim_next_render_job(WORKER_ID)
            if not job:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            job_id = int(job["id"])
            report_id = int(job["report_id"])
            params, formats = parse_job_payload(job)

            success, manifest, log_path, error = run_render_job(
                report_id=report_id,
                job_id=job_id,
                params=params,
                formats=formats,
            )
            manifest_path = write_manifest(report_id, manifest)

            if success:
                _update_success(report_id, job_id, manifest_path, manifest, log_path)
                print(f"Job {job_id} completed successfully")
            else:
                _update_failure(report_id, job_id, log_path, error or "Unknown render error")
                print(f"Job {job_id} failed: {error}")
        except Exception as ex:
            print(f"Worker loop error: {ex}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker_forever()
