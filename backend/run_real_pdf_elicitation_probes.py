"""Follow-up diagnostics on the saved real-PDF audit; never human observations."""
import asyncio
import json
import os
from pathlib import Path
import time

OUT = Path(os.getenv("ELICITATION_AUDIT_DIR", str(Path(__file__).resolve().parents[1] / "artifacts/real_pdf_elicitation_audit"))).resolve()
os.environ["DATABASE_PATH"] = str(OUT / "audit.sqlite")
os.environ["OLLAMA_MODEL"] = "qwen2.5:latest"
from ollama_client import ollama
from run_real_pdf_elicitation_audit import save
from epistemic_harness import LiteratureSource, LiteratureChunk, run_epistemic_gap_harness, normalize_paper_model
from adaptive_elicitation import create_session, answer_question, AnswerAdaptiveElicitationRequest


async def main():
    workspace = json.loads((OUT / "workspace.json").read_text(encoding="utf-8"))
    stage = "memory"
    number = 0
    generate = ollama.generate_json

    async def observed(prompt, **kwargs):
        nonlocal number
        number += 1
        base = OUT / f"probe_{number:02d}"
        save(base.with_suffix(".request.json"), {"stage": stage, "prompt": prompt, "kwargs": kwargs})
        started = time.monotonic()
        print(f"START {stage} {number}", flush=True)
        try:
            result = await generate(prompt, **kwargs)
            save(base.with_suffix(".response.json"), {"stage": stage, "payload": result, "elapsed_seconds": time.monotonic()-started})
            return result
        except Exception as exc:
            save(base.with_suffix(".error.json"), {"stage": stage, "error": repr(exc)})
            raise
        finally:
            save(OUT / "probe_metrics.json", ollama.metrics_snapshot())
            print(f"END {stage} {time.monotonic()-started:.1f}s", flush=True)

    ollama.generate_json = observed
    from main import infer_workspace_memory, _compact_explicit_state_for_prompt, _fallback_tacit_elicitation_questions
    from models import InferWorkspaceMemoryRequest
    result = await infer_workspace_memory(InferWorkspaceMemoryRequest(workspace_key="real-pdf-audit", explicit_state=workspace))
    save(OUT / "tacit_memory.json", result.model_dump())

    # Known-answer and provenance probes are controlled counterexamples, not a
    # model-quality benchmark. They exercise exactly the production validators.
    known = {**workspace, "adaptive_elicitation_session": {"answer_history": [{"question_id": "growth", "option_label": "No growth penalty acceptable"}]}}
    compact = _compact_explicit_state_for_prompt(known)
    sources = [LiteratureSource.model_validate(x) for x in json.loads((OUT / "harness_sources.json").read_text(encoding="utf-8"))]
    analyst_source = sources[1]
    analyst_chunk = next(c for c in analyst_source.chunks if c.kind == "analyst_gap")
    unsupported = normalize_paper_model(analyst_source, {"claims": [{"id": "adversarial", "proposition": "This paper proves that every yeast strain doubles naringenin production without any growth penalty.", "status": "supported", "chunk_ids": [analyst_chunk.id]}]})
    save(OUT / "deterministic_probes.json", {
        "synthetic_counterexamples": True,
        "adaptive_answer_history_survives_compaction": "adaptive_elicitation_session" in compact,
        "unsupported_claim_with_analyst_gap_citation_accepted": bool(unsupported.claims),
        "unsupported_claim_result": unsupported.model_dump(),
        "fallback_questions": [q.model_dump() for q in _fallback_tacit_elicitation_questions(workspace)],
    })

    # Diagnostic: direct PDF snippets bypass the UI's generated-summary handoff.
    # Exclude bibliography pages using the PDF's actual References heading.
    # Add a clearly labeled positive-control local preference, not an inferred
    # fact about the user's real project, to exercise question and answer paths.
    direct_sources = []
    for source in sources:
        annotations = json.loads((OUT / f"{source.id}_annotation.json").read_text(encoding="utf-8"))["annotations"]
        pages = json.loads((OUT / f"{source.id}_pages.json").read_text(encoding="utf-8"))
        import re
        reference_page = next((p["page"] for p in pages if re.search(r"(?im)^\s*references\s*$", p["text"])), len(pages)+1)
        chunks = [LiteratureChunk(id=f"{source.id}_page1", text=re.sub(r"\s+", " ", pages[0]["text"])[:2300])]
        chunks += [LiteratureChunk(id=f"{source.id}_page{a['page']}_passage{i+1}", text=a["snippet"]) for i,a in enumerate(annotations) if a["page"] < reference_page]
        direct_sources.append(LiteratureSource(id=source.id, citation=source.citation, chunks=chunks))
    direct_workspace = {"query": workspace["query"], "selected_project": workspace["selected_project"],
        "reasoning_notes": "TEST SCENARIO, NOT A REAL USER STATEMENT: We have records of the strain genotype and assay protocol. Before choosing the experiment, the program lead has not yet decided whether a slower-growing strain is acceptable in exchange for increased naringenin production. This is a preference to elicit, not a growth effect to assume."}
    save(OUT / "direct_pdf_positive_control_inputs.json", {"workspace": direct_workspace, "sources": [s.model_dump() for s in direct_sources], "diagnostic_only": True})
    stage = "direct_pdf_positive_control"
    try:
        result = await run_epistemic_gap_harness(workspace_context=direct_workspace, sources=direct_sources, generate_json=observed, max_concurrency=1)
        save(OUT / "direct_pdf_harness.json", result.model_dump())
        session = create_session(workspace_key="pdf-positive-control", context_digest=json.dumps(direct_workspace), raw_payload=result.elicitation_payload, generation_source="harness", max_questions=8, min_information_gain=0.04)
        save(OUT / "direct_pdf_session.json", session.model_dump())
        question = next((q for q in session.candidate_questions if q.id == session.current_question_id), None)
        branches = []
        if question:
            for option in question.answer_options:
                if option.allows_free_text:
                    continue
                after = answer_question(AnswerAdaptiveElicitationRequest(session=session.model_copy(deep=True), question_id=question.id, option_id=option.id))
                branches.append({"synthetic_branch_probe": True, "option": option.model_dump(), "after": after.model_dump()})
        save(OUT / "direct_pdf_answer_branches.json", branches)
    except Exception as exc:
        save(OUT / "direct_pdf_error.json", {"error": repr(exc)})
    await ollama.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
