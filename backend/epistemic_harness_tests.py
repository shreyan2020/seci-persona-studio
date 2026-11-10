"""Focused tests for the generative, provenance-constrained epistemic harness."""

import asyncio
import unittest

from adaptive_elicitation import create_session
from epistemic_harness import (
    LiteratureChunk,
    LiteratureSource,
    build_quantitative_repair_prompt,
    extract_literature_sources,
    normalize_paper_model,
    run_epistemic_gap_harness,
    unsupported_question_numbers,
)


class EpistemicHarnessTests(unittest.TestCase):
    def test_generated_quantitative_cutoffs_must_be_grounded(self):
        payload = {
            "belief_variables": [
                {
                    "label": "Acceptable biomass penalty is 10%",
                    "hypotheses": [{"proposition": "Use a 10% cutoff"}],
                }
            ],
            "candidate_questions": [
                {"question": "Is 10% acceptable?", "answer_options": [{"label": "10% or less"}]}
            ],
        }

        self.assertEqual(unsupported_question_numbers(payload, "No cutoff has been supplied."), ["10%"])
        self.assertEqual(unsupported_question_numbers(payload, "The approved cutoff is 10%."), [])
        repair_prompt = build_quantitative_repair_prompt(
            question_payload=payload,
            unsupported_numbers=["10%"],
        )
        self.assertNotIn("10%", repair_prompt)
        self.assertIn("[UNSUPPORTED_CUTOFF]", repair_prompt)

    def test_workspace_findings_become_typed_chunks(self):
        sources = extract_literature_sources(
            {
                "research_work_template": {
                    "literature_findings": [
                        {
                            "id": "paper-a",
                            "citation": "Controlled paper A",
                            "knowns": ["Increasing precursor supply increased product titre."],
                            "unknowns": ["The growth trade-off in the target strain is unknown."],
                            "annotation_insights": ["The reported host differed from the target host."],
                        }
                    ]
                }
            }
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual([chunk.kind for chunk in sources[0].chunks], ["evidence", "annotation", "analyst_gap"])
        self.assertTrue(all(chunk.id.startswith("paper_a_chunk_") for chunk in sources[0].chunks))

    def test_claim_without_valid_chunk_provenance_is_rejected(self):
        source = LiteratureSource(
            id="paper_a",
            citation="Controlled paper A",
            chunks=[LiteratureChunk(id="paper_a_chunk_1", text="Observed result")],
        )
        model = normalize_paper_model(
            source,
            {
                "claims": [
                    {
                        "id": "valid",
                        "proposition": "The paper reports an observed result.",
                        "chunk_ids": ["paper_a_chunk_1"],
                    },
                    {
                        "id": "hallucinated",
                        "proposition": "An unsupported result.",
                        "chunk_ids": ["missing_chunk"],
                    },
                ]
            },
        )

        self.assertEqual([claim.id for claim in model.claims], ["paper_a__valid"])
        self.assertEqual(model.rejected_claims[0]["claim_id"], "paper_a__hallucinated")

    def test_harness_only_turns_ask_user_gaps_into_dynamic_questions(self):
        sources = [
            LiteratureSource(
                id="paper_a",
                citation="Controlled precursor study",
                chunks=[
                    LiteratureChunk(
                        id="paper_a_chunk_1",
                        text="Increasing malonyl-CoA supply improved naringenin titre but reduced growth.",
                    )
                ],
            )
        ]

        async def fake_generate(prompt, **_kwargs):
            if "exactly one paper" in prompt:
                return {
                    "claims": [
                        {
                            "id": "precursor_tradeoff",
                            "proposition": "Increasing malonyl-CoA supply improved naringenin titre but reduced growth.",
                            "claim_type": "empirical_effect",
                            "status": "supported",
                            "chunk_ids": ["paper_a_chunk_1"],
                            "scope": {"outcome": "naringenin titre and growth"},
                            "evidence_strength": 0.7,
                            "extraction_confidence": 0.98,
                        }
                    ],
                    "gaps": [],
                }
            return {
                "world_summary": "Precursor engineering has a product-growth trade-off.",
                "claim_relations": [],
                "gaps": [
                    {
                        "id": "acceptable_growth_loss",
                        "statement": "The acceptable growth loss for the next screen is unspecified.",
                        "gap_type": "tacit",
                        "related_claim_ids": ["paper_a__precursor_tradeoff"],
                        "missing_premises": ["A locally acceptable growth threshold"],
                        "affected_decisions": ["Whether to prioritize malonyl-CoA engineering"],
                        "candidate_actions": ["ask_user"],
                        "recommended_action": "ask_user",
                        "routing_rationale": "This is a project-specific tolerance owned by the team.",
                        "decision_relevance": 0.95,
                        "user_answerability": 0.95,
                    },
                    {
                        "id": "target_strain_tradeoff",
                        "statement": "The actual growth penalty in the target strain is unknown.",
                        "gap_type": "empirical",
                        "related_claim_ids": ["paper_a__precursor_tradeoff"],
                        "missing_premises": ["A measurement in the target strain"],
                        "affected_decisions": ["Select the engineering route"],
                        "candidate_actions": ["run_experiment"],
                        "recommended_action": "run_experiment",
                        "routing_rationale": "Only a target-strain experiment can measure this effect.",
                        "decision_relevance": 0.9,
                        "user_answerability": 0.1,
                    },
                ],
                "belief_variables": [
                    {
                        "id": "growth_tolerance",
                        "label": "Acceptable growth penalty",
                        "gap_id": "acceptable_growth_loss",
                        "hypotheses": [
                            {"id": "strict", "proposition": "Growth loss above 5% is unacceptable", "probability": 0.5},
                            {"id": "permissive", "proposition": "Growth loss up to 20% is acceptable", "probability": 0.5},
                        ],
                    }
                ],
                "decision_actions": [
                    {"id": "precursor_first", "label": "Screen precursor engineering first", "loss_by_hypothesis": {"strict": 0.8, "permissive": 0.0}},
                    {"id": "enzyme_first", "label": "Screen enzyme expression first", "loss_by_hypothesis": {"strict": 0.0, "permissive": 0.5}},
                ],
                "candidate_questions": [
                    {
                        "id": "growth_threshold_for_naringenin_screen",
                        "gap_id": "acceptable_growth_loss",
                        "target_variable_id": "growth_tolerance",
                        "question": "For the next naringenin screen, what growth-rate penalty would make a malonyl-CoA intervention unacceptable?",
                        "why_it_matters": "The threshold changes which engineering route is screened first.",
                        "evidence_refs": ["paper_a__precursor_tradeoff"],
                        "resolution_rationale": "The literature cannot define the team's local trade-off.",
                        "alternative_resolution": "Compare both routes experimentally if no threshold exists.",
                        "answer_options": [
                            {"id": "strict_limit", "label": "More than 5%", "allows_free_text": False},
                            {"id": "permissive_limit", "label": "More than 20%", "allows_free_text": False},
                        ],
                        "predictions": [
                            {"hypothesis_id": "strict", "option_probabilities": {"strict_limit": 0.9, "permissive_limit": 0.1}},
                            {"hypothesis_id": "permissive", "option_probabilities": {"strict_limit": 0.1, "permissive_limit": 0.9}},
                        ],
                        "decision_relevance": 0.95,
                        "answerability": 0.95,
                        "estimated_effort_seconds": 15,
                    }
                ],
            }

        result = asyncio.run(
            run_epistemic_gap_harness(
                workspace_context={
                    "query": "Improve naringenin production in yeast",
                    "candidate_growth_thresholds": "Compare 5% and 20% growth-loss policies",
                },
                sources=sources,
                generate_json=fake_generate,
            )
        )

        self.assertEqual(result.elicitation_payload["candidate_questions"][0]["gap_id"], "acceptable_growth_loss")
        self.assertNotIn("target_strain_tradeoff", str(result.elicitation_payload["candidate_questions"]))
        self.assertEqual(result.trace()["routing_counts"], {"ask_user": 1, "run_experiment": 1})

        session = create_session(
            workspace_key="dynamic-biotech-test",
            context_digest="controlled naringenin scenario",
            raw_payload=result.elicitation_payload,
            generation_source="harness",
            max_questions=4,
            min_information_gain=0.0,
            min_geodesic_gain=0.0,
            max_normalized_uncertainty_for_stop=1.0,
            cost_per_second=0.0,
        )
        self.assertEqual(session.current_question_id, "growth_threshold_for_naringenin_screen")
        self.assertEqual(session.candidate_questions[0].gap_id, "acceptable_growth_loss")
        self.assertEqual(session.candidate_questions[0].evidence_refs, ["paper_a__precursor_tradeoff"])


if __name__ == "__main__":
    unittest.main()
