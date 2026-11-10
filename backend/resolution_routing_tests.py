import asyncio
import unittest
from adaptive_elicitation import create_session
from epistemic_harness import LiteratureSource, LiteratureChunk, normalize_synthesis, run_epistemic_gap_harness

class ResolutionRoutingTests(unittest.TestCase):
    def test_routes_skip_question_call(self):
        for action in ('run_experiment', 'search_literature', 'inspect_workspace', 'derive', 'align_constructs', 'compare_evidence', 'discover_hypothesis', 'stop'):
            with self.subTest(action=action):
                calls = []
                async def generate(prompt, **kwargs):
                    calls.append(prompt)
                    if len(calls) == 1:
                        return {'claims': [{'id': 'result', 'proposition': 'Growth changed.', 'chunk_ids': ['c1']}]}
                    if len(calls) == 2:
                        return {'gaps': [{'id': 'transfer', 'statement': 'Transfer unresolved', 'recommended_action': action, 'routing_rationale': 'Use the indicated resolver.'}]}
                    self.fail('Unnecessary question call')
                result = asyncio.run(run_epistemic_gap_harness(workspace_context={}, sources=[LiteratureSource(id='source', citation='Fixture', chunks=[LiteratureChunk(id='c1', text='Growth changed.')])], generate_json=generate))
                self.assertEqual(len(calls), 2)
                self.assertEqual(result.trace()['routing_counts'], {action: 1})
                session = self.session(result.elicitation_payload)
                self.assertEqual(session.status, 'complete')
                self.assertIsNone(session.current_question_id)
                self.assertEqual(session.candidate_questions, [])
                self.assertEqual(session.decision_actions, [])

    def session(self, payload, source='harness'):
        return create_session(workspace_key='test', context_digest='test', raw_payload=payload, generation_source=source, max_questions=4, min_information_gain=0.0)

    def test_invalid_routing_is_not_success(self):
        for raw in ({}, {'gaps': [{'recommended_action': 'invented'}]}, {'gaps': [{'id': 'x', 'recommended_action': 'ask_user', 'routing_rationale': 'User owns this'}]}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_synthesis(raw=raw, paper_models=[])

    def test_marker_cannot_bypass_model_validation(self):
        with self.assertRaises(ValueError):
            self.session({'resolution_only': True}, 'model')

    def test_contradictory_content_rejected(self):
        with self.assertRaises(ValueError):
            self.session({'resolution_only': True, 'candidate_questions': [{'id': 'unexpected'}]})
