"""Live regression on the prior two real PDFs; test answers are explicitly synthetic."""
import asyncio
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("RESEARCH_BOARD_OUTPUT", str(ROOT / "artifacts/research_board_live"))).resolve()
os.environ["OLLAMA_MODEL"] = "qwen2.5:latest"
os.environ["OLLAMA_NUM_CTX"] = "8192"
os.environ["DATABASE_PATH"] = str(OUT / "demo.sqlite")

from research_board import (BoardRepository, answer_board, confirmed_rule_context,
                           generate_board, review_rule, verified_pdf_evidence)
from research_tools import annotate_pdf_for_objective
from ollama_client import ollama
from run_real_pdf_elicitation_audit import PAPERS, QUERY, save


async def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise ValueError("Keep earlier live evidence; use a new output directory before rerunning.")
    OUT.mkdir(parents=True, exist_ok=True)
    call = 0
    stage = "pdf"
    original = ollama.generate_json
    async def observed(prompt, **kwargs):
        nonlocal call
        call += 1
        prefix = OUT / f"call_{call:02d}"
        save(prefix.with_suffix(".request.json"), {"stage": stage, "prompt": prompt, "kwargs": kwargs, "num_ctx": 8192})
        started = time.monotonic()
        print(f"START {stage} call {call}", flush=True)
        try:
            result = await original(prompt, **kwargs)
            save(prefix.with_suffix(".response.json"), {"stage": stage, "payload": result, "seconds": time.monotonic()-started})
            return result
        except Exception as exc:
            save(prefix.with_suffix(".error.json"), {"stage": stage, "error": repr(exc)})
            raise
        finally:
            print(f"END {stage} {time.monotonic()-started:.1f}s", flush=True)
            save(OUT / "metrics.json", ollama.metrics_snapshot())
    ollama.generate_json = observed
    save(OUT / "model_manifest.json", json.loads(urllib.request.urlopen(ollama.base_url+"/api/tags", timeout=10).read()))
    state = {"query": QUERY, "selected_project": {"project_goal": "Choose the first engineering experiment for naringenin", "target_host": "Saccharomyces cerevisiae", "end_product": "naringenin"}, "research_work_template": {"literature_findings": []}}
    for pid, title, doi, folder in PAPERS:
        stage = f"annotate_{pid}"
        path = ROOT / "backend/data/paper_evidence/project_3" / folder / "original.pdf"
        reuse = os.getenv("RESEARCH_BOARD_REUSE")
        if reuse:
            result = json.loads((Path(reuse)/f"{pid}_annotations.json").read_text(encoding="utf-8"))
        else:
            result = await annotate_pdf_for_objective(pdf_path=path, query=QUERY, project_goal=state["selected_project"]["project_goal"], project_end_product="naringenin", project_target_host="Saccharomyces cerevisiae", output_path=OUT/f"{pid}_annotated.pdf")
        save(OUT/f"{pid}_annotations.json", result)
        state["research_work_template"]["literature_findings"].append({"id": pid, "citation": f"{title}. DOI: {doi}", "knowns": [], "unknowns": result.get("research_questions", []), "annotations": result["annotations"], "annotation_insights": result["insights"], "structured_notes": result["structured_notes"]})
    save(OUT/"workspace.json", state)
    evidence = verified_pdf_evidence(state, ROOT / "backend/data/paper_evidence")
    save(OUT/"evidence.json", [e.model_dump() for e in evidence])
    stage = "board_round"
    board = await generate_board(workspace_key="real-pdf__research-board", state=state, evidence=evidence, generate=observed, model=ollama.model)
    repo = BoardRepository(str(OUT/"demo.sqlite"))
    board = repo.save(board, 0)
    save(OUT/"board_before_answer.json", board.model_dump())
    pending = next((q for q in board.questions if q.status == "pending"), None)
    if pending:
        # Software branch probe, not a claim about the user's lab or preferences.
        stage = "synthetic_answer_probe"
        draft = await answer_board(board, pending.id, "avoid", "", observed)
        save(OUT/"draft_before_confirmation.json", draft.model_dump())
        confirmed = review_rule(draft, draft.rules[-1].id, "confirm")
        confirmed = repo.save(confirmed, board.revision)
        reloaded = repo.get(board.workspace_key)
        save(OUT/"board_after_confirmation.json", reloaded.model_dump())
        save(OUT/"probe_result.json", {"synthetic_answer_not_user_data": True,
            "draft_did_not_apply": all(a.disposition == "eligible" for a in draft.actions),
            "confirmed_exclusion_applied": [a.id for a in reloaded.actions if a.disposition == "excluded"],
            "context_for_next_run": confirmed_rule_context(reloaded)})
    else:
        save(OUT/"probe_result.json", {"no_pending_question": True, "note": "No question was manually supplied. Answer/confirmation checks remain covered by deterministic tests."})
    await ollama.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
