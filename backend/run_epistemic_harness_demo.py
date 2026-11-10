"""Run a controlled biotech example through the live local generative harness."""

import asyncio
import json

from adaptive_elicitation import create_session
from database import db
from epistemic_harness import extract_literature_sources, harness_run_id, run_epistemic_gap_harness
from ollama_client import ollama


WORKSPACE = {
    "query": (
        "For a Saccharomyces cerevisiae naringenin program, which first validation experiment should we prioritize: "
        "increasing malonyl-CoA supply or testing product export?"
    ),
    "selected_project": {
        "project_goal": "Choose one two-week validation experiment before committing the strain-engineering roadmap.",
        "target_host": "Saccharomyces cerevisiae",
        "end_product": "naringenin",
    },
    "unresolved_user_owned_decisions": [
        "Only the program lead can specify the maximum acceptable biomass penalty for the two-week validation screen; this threshold is not stored in the workspace."
    ],
    "research_work_template": {
        "literature_findings": [
            {
                "id": "precursor-study",
                "citation": "Controlled test source: precursor-supply study",
                "knowns": [
                    "In the reported yeast strain, increasing malonyl-CoA availability increased naringenin titre, while the strongest intervention also reduced biomass accumulation."
                ],
                "unknowns": [
                    "The acceptable biomass penalty and the effect size in the workspace strain are not stated."
                ],
                "annotation_insights": [
                    "The study used a different parental strain and a longer cultivation window than the workspace protocol."
                ],
            },
            {
                "id": "export-study",
                "citation": "Controlled test source: product-export study",
                "knowns": [
                    "Expression of a candidate exporter reduced intracellular flavonoid accumulation under the reported assay conditions."
                ],
                "unknowns": [
                    "The source does not establish whether export increased total naringenin titre or only changed its intra- versus extracellular distribution."
                ],
                "annotation_insights": [
                    "The workspace does not state whether its assay measures extracellular product, intracellular product, or both."
                ],
            },
        ]
    },
}


async def main() -> None:
    sources = extract_literature_sources(WORKSPACE)

    async def generate_cached(prompt: str, **kwargs):
        kwargs.setdefault("model", "qwen2.5:latest")
        return await ollama.generate_json_cached(
            cache=db,
            task_type="epistemic_gap_harness_demo",
            prompt=prompt,
            cache_version=1,
            cache_inputs={"scenario": "naringenin_two_source_v1"},
            **kwargs,
        )

    result = await run_epistemic_gap_harness(
        workspace_context=WORKSPACE,
        sources=sources,
        generate_json=generate_cached,
        max_concurrency=1,
    )
    session = create_session(
        workspace_key="demo-naringenin",
        context_digest=json.dumps(WORKSPACE, ensure_ascii=False),
        raw_payload=result.elicitation_payload,
        generation_source="harness",
        max_questions=6,
        min_information_gain=0.0,
        min_geodesic_gain=0.0,
        max_normalized_uncertainty_for_stop=1.0,
        cost_per_second=0.001,
    )
    current = next(
        (question for question in session.candidate_questions if question.id == session.current_question_id),
        None,
    )
    output = {
        "run_id": harness_run_id(result),
        "question": WORKSPACE["query"],
        "world_summary": result.world_summary,
        "source_worlds": len(result.paper_models),
        "accepted_claims": sum(len(model.claims) for model in result.paper_models),
        "rejected_claims": sum(len(model.rejected_claims) for model in result.paper_models),
        "gap_routes": [
            {
                "id": gap.id,
                "type": gap.gap_type,
                "route": gap.recommended_action,
                "statement": gap.statement,
            }
            for gap in result.gaps
        ],
        "generated_questions": [
            {
                "id": question.id,
                "gap_id": question.gap_id,
                "question": question.question,
                "evidence_refs": question.evidence_refs,
                "robust_evsi": question.robust_bayes_risk_reduction,
                "net_value": question.net_value,
            }
            for question in session.candidate_questions
        ],
        "belief_variables": [variable.model_dump() for variable in session.belief_variables],
        "decision_actions": [action.model_dump() for action in session.decision_actions],
        "selected_question": current.model_dump() if current else None,
        "stopping_reason": session.stopping_reason,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
