# Architecture

## Evidence and decisions

The project page in `frontend/src/app/page.tsx` manages the current project, research question, literature library, and saved workspace. **Prepare evidence** uses the current library, searches when it is empty, prepares eligible PDFs, and saves experiment comparisons before requesting perspectives. Completed stages remain saved if a later stage fails.

The backend reuses downloaded PDFs, parses documents with LiteParse, and caches source passages. Before admitting evidence to a research board, it checks the original PDF hash, page, and normalized quotation. Fact extraction retains exact source spans. Experiment linking accepts same-paper groups with shared explicit anchors and rejects incompatible conditions. Unlinked facts remain available separately.

Three role prompts run concurrently over shared evidence and an action catalog. The first-round roles do not see each other's responses. Claim-support checks and a subsequent review can reject contributions, challenge proposals, or ask for an unresolved local constraint or experience. Researchers can also select a reported condition and record how it relates to their setup.

Researcher answers can produce draft rules. Confirmation applies a rule to the named actions in the current decision; revocation recomputes eligibility. SQLite stores board revisions and history, and stale updates return a conflict. Exact quotation checks establish source location; interpretations still need scientific review.

## Code map

| Location | Responsibility |
| --- | --- |
| `frontend/src/features/biotech-workspace/` | Project UI, evidence comparison, research discussion, API client, and state helpers |
| `frontend/src/app/examples/itaconate/` | Read-only example using the workspace's comparison and discussion components |
| `backend/main.py` | FastAPI application and project, literature, document, and report endpoints |
| `backend/research_tools.py`, `document_pipeline.py` | Literature access, PDF preparation, parsing, and passage caches |
| `backend/research_board.py`, `research_board_api.py` | Concurrent roles, review, questions, rules, persistence, and board API |
| `backend/evidence_grounding.py`, `evidence_comparison.py`, `comparison_models.py` | Claim checks, extracted facts, experiment records, and researcher comparisons |
| `backend/agent_execution.py`, `project_workflows.py` | Staged project execution and saved work templates |
| `backend/database.py`, `context_fs.py`, `paper_storage.py` | SQLite and local artifact storage |
| `backend/report_service.py`, `quarto_service.py`, `worker_runner.py` | Report records, rendering jobs, and background processing |
| `backend/tests/`, `frontend/tests/` | Application regression tests |

## Configuration

`OLLAMA_MODEL` selects the default installed model. `OLLAMA_EXTRACTION_MODEL`, `OLLAMA_PERSPECTIVE_MODEL`, and `OLLAMA_REVIEW_MODEL` optionally select separate installed models for those operations. Blank overrides inherit the default. The shared Ollama client limits concurrent work and caches identical requests.

PDF originals and annotations are stored locally. `PAPER_EVIDENCE_ROOT` selects their location; `DOCUMENT_CACHE_ROOT` overrides the parser cache. Cache identity includes source bytes, parser settings, and model identity. Set `OLLAMA_MODEL_REVISION` when replacing model weights under an existing tag.

For Docker, copy `.env.example` to `.env`, review its settings, and run `docker compose up --build -d`. Compose starts nginx, frontend, backend, the report worker, and Ollama. The supplied Ollama service requests NVIDIA GPU access; adjust it for a CPU-only host and pull the configured model. The backend and worker share the data volume.

The desktop wrapper and packaging commands are documented in [Electron setup](../frontend/ELECTRON.md).
