"""Bounded PDF attachment storage, independent of model generation."""
from pathlib import Path
import hashlib
import os
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File
from paper_storage import paper_evidence_root


def paper_upload_router(get_project):
    router = APIRouter()
    @router.post("/api/projects/{project_id}/literature/upload")
    async def upload_literature_pdf(project_id: int, file: UploadFile = File(...)):
        if not get_project(project_id):
            raise HTTPException(404, "Project not found")
        root = paper_evidence_root() / f"project_{project_id}"
        root.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest = hashlib.sha256()
            size = 0
            with tempfile.NamedTemporaryFile(dir=root, suffix=".pdf", delete=False) as output:
                temporary = Path(output.name)
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 30 * 1024 * 1024:
                        raise HTTPException(413, "PDF must be at most 30 MB")
                    digest.update(chunk)
                    output.write(chunk)
            import fitz
            try:
                with fitz.open(temporary) as document:
                    if not document.is_pdf or document.needs_pass or not len(document):
                        raise ValueError("Unreadable PDF")
            except Exception as exc:
                raise HTTPException(422, "Upload a readable, unencrypted PDF") from exc
            paper_id = "upload_" + digest.hexdigest()
            folder = root / paper_id
            folder.mkdir(exist_ok=True)
            os.replace(temporary, folder / "original.pdf")
            return {"paper_id": paper_id}
        finally:
            await file.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return router
