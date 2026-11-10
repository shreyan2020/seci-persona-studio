"""Focused tests for adaptive Bayesian question selection."""

import unittest

from adaptive_elicitation import (
    AnswerAdaptiveElicitationRequest,
    answer_question,
    bayes_risk,
    create_session,
    decision_value_metrics,
    entropy,
    fisher_rao_distance,
    fallback_payload,
    geometric_novelty,
    normalized_entropy,
)


class AdaptiveElicitationTests(unittest.TestCase):
    def make_decision_payload(self, *, question_cost: float = 0.0, include_ambiguous_model: bool = False):
        question = {
            "id": "discriminate_preference",
            "target_variable_id": "preference",
            "question": "Which option should govern the decision?",
            "answer_options": [
                {"id": "option_a", "label": "Option A"},
                {"id": "option_b", "label": "Option B"},
            ],
            "predictions": [
                {"hypothesis_id": "a", "option_probabilities": {"option_a": 1.0, "option_b": 0.0}},
                {"hypothesis_id": "b", "option_probabilities": {"option_a": 0.0, "option_b": 1.0}},
            ],
            "answerability": 1.0,
            "decision_relevance": 1.0,
            "estimated_effort_seconds": 1.0,
            "question_cost": question_cost,
        }
        if include_ambiguous_model:
            question["likelihood_models"] = [
                {
                    "id": "ambiguous",
                    "predictions": [
                        {"hypothesis_id": "a", "option_probabilities": {"option_a": 0.5, "option_b": 0.5}},
                        {"hypothesis_id": "b", "option_probabilities": {"option_a": 0.5, "option_b": 0.5}},
                    ],
                }
            ]
        return {
            "belief_variables": [
                {
                    "id": "preference",
                    "label": "Preference",
                    "hypotheses": [
                        {"id": "a", "proposition": "Option A is best", "probability": 0.5},
                        {"id": "b", "proposition": "Option B is best", "probability": 0.5},
                    ],
                }
            ],
            "decision_worlds": [
                {
                    "id": "world_a",
                    "label": "A is best",
                    "probability": 0.5,
                    "hypothesis_assignments": {"preference": "a"},
                },
                {
                    "id": "world_b",
                    "label": "B is best",
                    "probability": 0.5,
                    "hypothesis_assignments": {"preference": "b"},
                },
            ],
            "decision_actions": [
                {"id": "choose_a", "label": "Choose A", "loss_by_world": {"world_a": 0.0, "world_b": 1.0}},
                {"id": "choose_b", "label": "Choose B", "loss_by_world": {"world_a": 1.0, "world_b": 0.0}},
            ],
            "candidate_questions": [question],
        }

    def make_decision_session(self, payload=None, **overrides):
        return create_session(
            workspace_key="decision-test",
            context_digest="decision-aware",
            raw_payload=payload or self.make_decision_payload(),
            generation_source="model",
            max_questions=4,
            min_information_gain=overrides.pop("min_information_gain", 0.0),
            min_geodesic_gain=overrides.pop("min_geodesic_gain", 0.0),
            max_normalized_uncertainty_for_stop=overrides.pop(
                "max_normalized_uncertainty_for_stop", 1.0
            ),
            cost_per_second=overrides.pop("cost_per_second", 0.0),
            **overrides,
        )

    def make_session(
        self,
        *,
        min_information_gain: float = 0.04,
        min_geodesic_gain: float = 0.02,
        max_normalized_uncertainty_for_stop: float = 0.55,
    ):
        return create_session(
            workspace_key="project-1__query-1__persona-1",
            context_digest="high yield yeast route with a rapid proof-of-concept goal",
            raw_payload=fallback_payload(
                {
                    "query": "Find a high yield yeast route quickly",
                    "selected_project": {"project_goal": "Rapid proof of concept"},
                }
            ),
            generation_source="fallback",
            max_questions=8,
            min_information_gain=min_information_gain,
            min_geodesic_gain=min_geodesic_gain,
            max_normalized_uncertainty_for_stop=max_normalized_uncertainty_for_stop,
        )

    def test_entropy_is_measured_in_bits(self):
        self.assertAlmostEqual(entropy([0.5, 0.5]), 1.0)
        self.assertAlmostEqual(entropy([1.0, 0.0]), 0.0)

    def test_normalized_entropy_is_comparable_across_simplexes(self):
        self.assertAlmostEqual(normalized_entropy([0.5, 0.5]), 1.0)
        self.assertAlmostEqual(normalized_entropy([1 / 3, 1 / 3, 1 / 3]), 1.0)

    def test_fisher_rao_distance_is_intrinsic_and_bounded(self):
        self.assertAlmostEqual(fisher_rao_distance([0.5, 0.5], [0.5, 0.5]), 0.0)
        self.assertAlmostEqual(fisher_rao_distance([1.0, 0.0], [0.0, 1.0]), 3.141592653589793)

    def test_session_normalizes_beliefs_and_selects_question(self):
        session = self.make_session()
        self.assertEqual(session.status, "active")
        self.assertIsNotNone(session.current_question_id)
        self.assertGreater(session.initial_entropy, 0.0)
        for variable in session.belief_variables:
            self.assertAlmostEqual(sum(item.probability for item in variable.hypotheses), 1.0)
        selected = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        self.assertGreater(selected.expected_information_gain, 0.0)
        self.assertGreater(selected.expected_geodesic_gain, 0.0)
        self.assertGreater(session.normalized_uncertainty, 0.0)
        self.assertGreater(selected.selection_score, 0.0)

    def test_answer_updates_posterior_and_reduces_uncertainty(self):
        session = self.make_session()
        question = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        answer = next(item for item in question.answer_options if not item.allows_free_text)
        updated = answer_question(
            AnswerAdaptiveElicitationRequest(
                session=session,
                question_id=question.id,
                option_id=answer.id,
            )
        )
        self.assertEqual(len(updated.answer_history), 1)
        self.assertGreater(updated.answer_history[0].information_gain, 0.0)
        self.assertGreater(updated.answer_history[0].belief_shift, 0.0)
        self.assertLess(updated.current_entropy, updated.initial_entropy)
        self.assertNotEqual(updated.current_question_id, question.id)

    def test_other_option_requires_explanation(self):
        session = self.make_session()
        question = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        other = next(item for item in question.answer_options if item.allows_free_text)
        with self.assertRaisesRegex(ValueError, "requires a short explanation"):
            answer_question(
                AnswerAdaptiveElicitationRequest(
                    session=session,
                    question_id=question.id,
                    option_id=other.id,
                )
            )

    def test_other_option_expands_hypothesis_space(self):
        session = self.make_session()
        question = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        other = next(item for item in question.answer_options if item.allows_free_text)
        variable = next(item for item in session.belief_variables if item.id == question.target_variable_id)
        original_count = len(variable.hypotheses)
        updated = answer_question(
            AnswerAdaptiveElicitationRequest(
                session=session,
                question_id=question.id,
                option_id=other.id,
                free_text="Minimize regulatory uncertainty before optimizing performance",
            )
        )
        updated_variable = next(item for item in updated.belief_variables if item.id == question.target_variable_id)
        self.assertEqual(len(updated_variable.hypotheses), original_count + 1)
        self.assertEqual(updated_variable.hypotheses[-1].probability, 0.7)
        self.assertIn("regulatory uncertainty", updated_variable.hypotheses[-1].proposition)
        self.assertTrue(any(item.id.startswith("discriminate_discovered_") for item in updated.candidate_questions))

    def test_duplicate_question_has_no_geometric_novelty(self):
        session = self.make_session()
        question = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        variable = next(item for item in session.belief_variables if item.id == question.target_variable_id)
        session.candidate_questions = [
            item.model_copy(update={"status": "answered"}) if item.id == question.id else item
            for item in session.candidate_questions
        ]
        duplicate = question.model_copy(update={"id": f"{question.id}_duplicate", "status": "candidate"})
        self.assertAlmostEqual(geometric_novelty(session, variable, duplicate), 0.0)

    def test_high_uncertainty_with_flat_questions_enters_discovery_mode(self):
        raw_payload = {
            "belief_variables": [
                {
                    "id": "decision",
                    "label": "Decision",
                    "hypotheses": [
                        {"id": "a", "proposition": "Option A matters", "probability": 0.5},
                        {"id": "b", "proposition": "Option B matters", "probability": 0.5},
                    ],
                }
            ],
            "candidate_questions": [
                {
                    "id": "flat",
                    "target_variable_id": "decision",
                    "question": "A question that cannot discriminate?",
                    "answer_options": [
                        {"id": "yes", "label": "Yes"},
                        {"id": "no", "label": "No"},
                    ],
                    "predictions": [
                        {"hypothesis_id": "a", "option_probabilities": {"yes": 0.5, "no": 0.5}},
                        {"hypothesis_id": "b", "option_probabilities": {"yes": 0.5, "no": 0.5}},
                    ],
                }
            ],
        }
        session = create_session(
            workspace_key="discovery",
            context_digest="ambiguous",
            raw_payload=raw_payload,
            generation_source="fallback",
            max_questions=8,
            min_information_gain=0.04,
            min_geodesic_gain=0.02,
            max_normalized_uncertainty_for_stop=0.55,
        )
        self.assertEqual(session.status, "active")
        self.assertEqual(session.selection_mode, "discovery")
        self.assertEqual(session.current_question_id, "discover_decision")

    def test_stops_when_information_threshold_is_not_met(self):
        session = self.make_session(
            min_information_gain=1.0,
            min_geodesic_gain=10.0,
            max_normalized_uncertainty_for_stop=1.0,
        )
        self.assertEqual(session.status, "complete")
        self.assertIsNone(session.current_question_id)
        self.assertIn("Normalized uncertainty", session.stopping_reason or "")

    def test_decision_value_measures_bayes_risk_reduction_and_action_change(self):
        session = self.make_decision_session()
        question = session.candidate_questions[0]
        risk, action_id = bayes_risk(session.decision_worlds, session.decision_actions)
        evsi, action_change_probability = decision_value_metrics(session, question)

        self.assertAlmostEqual(risk, 0.5)
        self.assertEqual(action_id, "choose_a")
        self.assertAlmostEqual(evsi, 0.5)
        self.assertAlmostEqual(action_change_probability, 0.5)

    def test_robust_likelihood_ensemble_uses_conservative_value(self):
        session = self.make_decision_session(
            payload=self.make_decision_payload(include_ambiguous_model=True),
            robust_quantile=0.1,
        )
        question = session.candidate_questions[0]

        self.assertAlmostEqual(question.expected_bayes_risk_reduction, 0.5)
        self.assertAlmostEqual(question.robust_bayes_risk_reduction, 0.0)
        self.assertLess(question.robust_bayes_risk_reduction, question.expected_bayes_risk_reduction)

    def test_question_cost_can_make_stopping_better_than_asking(self):
        session = self.make_decision_session(payload=self.make_decision_payload(question_cost=0.6))
        question = session.candidate_questions[0]

        self.assertEqual(session.status, "complete")
        self.assertIsNone(session.current_question_id)
        self.assertAlmostEqual(question.robust_bayes_risk_reduction, 0.5)
        self.assertAlmostEqual(question.net_value, -0.1)
        self.assertIn("Asking is not better than stopping", session.stopping_reason or "")

    def test_legacy_payload_derives_decision_worlds_and_actions(self):
        session = self.make_session()

        self.assertEqual(session.decision_model_source, "derived")
        self.assertGreater(len(session.decision_worlds), 0)
        self.assertEqual(len(session.decision_actions), len(session.decision_worlds))
        self.assertEqual(session.status, "active")
        selected = next(item for item in session.candidate_questions if item.id == session.current_question_id)
        self.assertGreater(selected.robust_bayes_risk_reduction, 0.0)
        self.assertGreater(selected.net_value, 0.0)


if __name__ == "__main__":
    unittest.main()
