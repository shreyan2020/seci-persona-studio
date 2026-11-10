"""Shared PDF storage location for preparation, serving, and board verification."""
import os
from pathlib import Path


def paper_evidence_root() -> Path:
    # Preserve the existing writer's cwd-relative default, including Electron's
    # writable runtime directory. Never infer storage from the module location.
    return Path(os.getenv("PAPER_EVIDENCE_ROOT") or "data/paper_evidence").resolve()
