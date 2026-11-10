"""Reproducible local-model audit using existing PDF and elicitation modules.

No real user answers or scientific ground truth are simulated as observations.
Model prompts, responses, failures, PDF hashes and intermediate states are saved.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PAPERS = [
    ("koopman2012", "De novo production of the flavonoid naringenin in engineered Saccharomyces cerevisiae", "10.1186/1475-2859-11-155", "PMC3539886"),
    ("liu2019", "Rewiring carbon metabolism in yeast for high level production of aromatic chemicals", "10.1038/s41467-019-12961-5", "PMID31672987"),
]
QUERY = "For glucose-derived naringenin production in Saccharomyces cerevisiae, should our first strain-engineering experiment increase aromatic precursor supply or balance the downstream naringenin pathway? What evidence transfers across these papers, what requires measurement in our strain, and what local judgments are still needed?"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def run(args):
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose an empty output directory so earlier evidence is not overwritten.")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_PATH"] = str(out / "audit.sqlite")
    os.environ["OLLAMA_MODEL"] = args.model
    import fitz
    from ollama_client import ollama
    from research_tools import annotate_pdf_for_objective
    from scientific_pdf_parsing import parse_scientific_pdf
    from epistemic_harness import extract_literature_sources, run_epistemic_gap_harness
    from adaptive_elicitation import create_session, answer_question, AnswerAdaptiveElicitationRequest

    stage = "initialization"
    call_number = 0
    original_json = ollama.generate_json
    original_generate = ollama.generate

    async def observed_generate(prompt, **kwargs):
        response = await original_generate(prompt, **kwargs)
        save(out / f"call_{call_number:02d}_raw.json", {"stage": stage, "response": response})
        return response

    async def observed_json(prompt, **kwargs):
        nonlocal call_number
        call_number += 1
        prefix = out / f"call_{call_number:02d}"
        started = time.monotonic()
        save(prefix.with_suffix(".request.json"), {"stage": stage, "prompt": prompt, "kwargs": kwargs})
        print(f"START {stage} call={call_number}", flush=True)
        try:
            value = await original_json(prompt, **kwargs)
            save(prefix.with_suffix(".response.json"), {"stage": stage, "elapsed_seconds": time.monotonic()-started, "payload": value})
            return value
        except Exception as exc:
            save(prefix.with_suffix(".error.json"), {"stage": stage, "elapsed_seconds": time.monotonic()-started, "error": repr(exc)})
            raise
        finally:
            save(out / "metrics.json", ollama.metrics_snapshot())
            print(f"END {stage} elapsed={time.monotonic()-started:.1f}s", flush=True)

    ollama.generate_json = observed_json
    ollama.generate = observed_generate
    tags = json.loads(urllib.request.urlopen(ollama.base_url + "/api/tags", timeout=10).read())
    manifest = {"model": next(m for m in tags["models"] if m["name"] == args.model), "query": QUERY,
                "scope": "Existing annotation module and elicitation functions; no browser interaction or paper search/download.",
                "papers": [], "environment": {key: os.getenv(key) for key in ["ENABLE_PDF_PASSAGE_PROMPTS_LLM", "DISABLE_PDF_NOTES_LLM", "DOCLING_ENABLED", "GROBID_URL", "DOCLING_URL"]}}
    workspace = {"query": QUERY, "selected_project": {"project_goal": "Choose the first strain-engineering experiment for glucose-derived naringenin.", "target_host": "Saccharomyces cerevisiae", "end_product": "naringenin"}, "research_work_template": {"literature_findings": []}}
    # The decision is a test scenario. No unpublished constraints or desired gaps
    # are supplied to the model, unlike the previous controlled demo.
    for paper_id, title, doi, folder in PAPERS:
        pdf = ROOT / "backend/data/paper_evidence/project_3" / folder / "original.pdf"
        doc = fitz.open(pdf)
        pages = [{"page": i+1, "text": page.get_text()} for i, page in enumerate(doc)]
        save(out / f"{paper_id}_pages.json", pages)
        doc[0].get_pixmap(matrix=fitz.Matrix(1, 1)).save(out / f"{paper_id}_first_page.png")
        manifest["papers"].append({"id": paper_id, "title": title, "doi": doi, "path": str(pdf), "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": len(doc)})
        doc.close()
        save(out / "manifest.json", manifest)
        try:
            parsed = await parse_scientific_pdf(pdf)
            save(out / f"{paper_id}_scientific_parser.json", parsed)
        except Exception as exc:
            save(out / f"{paper_id}_scientific_parser.json", {"error": str(exc), "impact": "Strict SOTA PDF preparation would stop here. Standard annotation below uses PyMuPDF."})
        stage = f"pdf_annotation_{paper_id}"
        result = await annotate_pdf_for_objective(pdf_path=pdf, query=QUERY,
            project_goal=workspace["selected_project"]["project_goal"], project_end_product="naringenin",
            project_target_host="Saccharomyces cerevisiae", output_path=out / f"{paper_id}_annotated.pdf",
            max_annotations=8, strict_llm_notes=False)
        save(out / f"{paper_id}_annotation.json", result)
        # Mirror the frontend's PDF-preparation update. Structured notes are not
        # silently inserted into knowns; the current UI preserves existing knowns.
        workspace["research_work_template"]["literature_findings"].append({"id": paper_id, "citation": f"{title}. DOI: {doi}", "knowns": [], "unknowns": result.get("research_questions", []), "annotation_insights": result.get("insights", []), "annotations": result.get("annotations", [])})
    save(out / "workspace.json", workspace)
    sources = extract_literature_sources(workspace)
    save(out / "harness_sources.json", [s.model_dump() for s in sources])
    stage = "adaptive_harness_pdf_ui_mapping"
    try:
        result = await run_epistemic_gap_harness(workspace_context=workspace, sources=sources, generate_json=observed_json, max_concurrency=1)
        save(out / "harness_result.json", result.model_dump())
        session = create_session(workspace_key="real-pdf-audit", context_digest=json.dumps(workspace), raw_payload=result.elicitation_payload, generation_source="harness", max_questions=8, min_information_gain=0.04)
        save(out / "session.json", session.model_dump())
        current = next((q for q in session.candidate_questions if q.id == session.current_question_id), None)
        if current:
            branches = []
            for option in current.answer_options:
                if option.allows_free_text:
                    continue
                after = answer_question(AnswerAdaptiveElicitationRequest(session=session.model_copy(deep=True), question_id=current.id, option_id=option.id))
                branches.append({"synthetic_branch_probe": True, "option": option.model_dump(), "session": after.model_dump()})
            save(out / "answer_branch_probes.json", branches)
    except Exception as exc:
        save(out / "harness_error.json", {"error": repr(exc)})
        print(f"HARNESS FAILED: {exc}", flush=True)
    # Exercise the separate workspace-memory path, using its normal behavior.
    stage = "workspace_tacit_memory"
    try:
        from main import infer_workspace_memory
        from models import InferWorkspaceMemoryRequest
        result = await infer_workspace_memory(InferWorkspaceMemoryRequest(workspace_key="real-pdf-audit", explicit_state=workspace, existing_tacit_state=[]))
        save(out / "tacit_memory.json", result.model_dump())
    except Exception as exc:
        save(out / "tacit_memory_error.json", {"error": repr(exc)})
    save(out / "metrics.json", ollama.metrics_snapshot())
    await ollama.close()
    print(f"DONE {out}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.getenv("ELICITATION_AUDIT_DIR", str(ROOT / "artifacts/real_pdf_elicitation_audit")))
    parser.add_argument("--model", default="qwen2.5:latest")
    asyncio.run(run(parser.parse_args()))
