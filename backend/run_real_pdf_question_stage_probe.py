"""Isolate question generation with a supplied gap after discovery failed.

This cannot be scored as autonomous gap discovery. All answers are branch probes.
"""
import asyncio
import json
import os
from pathlib import Path
import time

OUT = Path(os.getenv("ELICITATION_AUDIT_DIR", str(Path(__file__).resolve().parents[1] / "artifacts/real_pdf_elicitation_audit"))).resolve()
os.environ["OLLAMA_MODEL"] = "qwen2.5:latest"
from ollama_client import ollama
from run_real_pdf_elicitation_audit import save
from epistemic_harness import (PaperWorldModel, build_dynamic_question_prompt,
    normalize_synthesis, unsupported_question_numbers, build_quantitative_repair_prompt)
from adaptive_elicitation import create_session, answer_question, AnswerAdaptiveElicitationRequest


async def main():
    inputs = json.loads((OUT / "direct_pdf_positive_control_inputs.json").read_text(encoding="utf-8"))
    trace = json.loads((OUT / "direct_pdf_harness.json").read_text(encoding="utf-8"))
    models = [PaperWorldModel.model_validate(m) for m in trace["paper_models"]]
    gap_analysis = {"world_summary": "Isolated question-stage test with an evaluator-supplied user-owned gap.", "gaps": [{
        "id": "growth_tolerance", "statement": "The program lead has not set whether slower growth is acceptable for higher naringenin production.",
        "gap_type": "tacit", "related_claim_ids": [c.id for m in models for c in m.claims],
        "missing_premises": ["User-owned growth versus product trade-off"], "affected_decisions": ["Choose the first strain-engineering experiment"],
        "candidate_actions": ["ask_user"], "recommended_action": "ask_user",
        "routing_rationale": "A local preference cannot be settled by a paper or by measuring a growth effect.",
        "user_answerability": 1.0,
    }]}
    save(OUT / "supplied_gap.json", {"evaluator_supplied_not_discovered": True, "payload": gap_analysis})
    number = 0
    async def observed(prompt, **kwargs):
        nonlocal number
        number += 1
        base = OUT / f"question_probe_{number:02d}"
        save(base.with_suffix(".request.json"), {"prompt": prompt, "kwargs": kwargs})
        started = time.monotonic()
        print(f"START question probe {number}", flush=True)
        try:
            result = await ollama.generate_json(prompt, **kwargs)
            save(base.with_suffix(".response.json"), {"elapsed_seconds": time.monotonic()-started, "payload": result})
            return result
        except Exception as exc:
            save(base.with_suffix(".error.json"), {"error": repr(exc)})
            raise

    try:
        payload = await observed(build_dynamic_question_prompt(workspace_context=inputs["workspace"], paper_models=models, gap_analysis=gap_analysis), max_retries=0, temperature=0.15, top_p=0.85, timeout_seconds=300, num_predict=1600)
        grounding = json.dumps(inputs, ensure_ascii=False)
        unsupported = unsupported_question_numbers(payload, grounding)
        if unsupported:
            payload = await observed(build_quantitative_repair_prompt(question_payload=payload, unsupported_numbers=unsupported), max_retries=0, temperature=0.05, top_p=0.8, timeout_seconds=240, num_predict=1300)
            if unsupported_question_numbers(payload, grounding) or "[UNSUPPORTED_CUTOFF]" in json.dumps(payload):
                raise ValueError("Question probe failed quantitative grounding after repair")
        result = normalize_synthesis(raw={**gap_analysis, **payload}, paper_models=models)
        save(OUT / "supplied_gap_harness.json", result.model_dump())
        session = create_session(workspace_key="supplied-gap-probe", context_digest=json.dumps(inputs["workspace"]), raw_payload=result.elicitation_payload, generation_source="harness", max_questions=8, min_information_gain=0.04)
        save(OUT / "supplied_gap_session.json", session.model_dump())
        question = next((q for q in session.candidate_questions if q.id == session.current_question_id), None)
        branches = []
        if question:
            for option in question.answer_options:
                free_text = "I cannot specify a trade-off without reviewing a previous failed strain." if option.allows_free_text else ""
                after = answer_question(AnswerAdaptiveElicitationRequest(session=session.model_copy(deep=True), question_id=question.id, option_id=option.id, free_text=free_text))
                branches.append({"synthetic_not_user_data": True, "option": option.model_dump(), "free_text": free_text, "after": after.model_dump()})
        save(OUT / "supplied_gap_answer_branches.json", branches)
    except Exception as exc:
        save(OUT / "supplied_gap_error.json", {"error": repr(exc)})
    save(OUT / "question_probe_metrics.json", ollama.metrics_snapshot())
    await ollama.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
