import asyncio
import unittest
from unittest.mock import AsyncMock
from evidence_grounding import relevant_evidence, structural_problem, supported_items
from research_board import BoardEvidence, generate_board


def protein_source():
    return BoardEvidence(id='e1', source_id='protein', citation='Misleading itaconic acid caption', page=1,
        quote='Production of secretable TAT-fusion proteins by engineered mammalian cells.', source_sha256='hash',
        document_context='Secretion and uptake of TAT-fusion proteins produced by engineered mammalian cells.')


class GroundingTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_failures_are_distinguished_from_unsupported_claims(self):
        item = {'id':'p','text':'Interpretation','evidence_refs':['e1']}
        diagnostics = []
        await supported_items([item], [protein_source()], {}, AsyncMock(side_effect=RuntimeError()), diagnostics)
        self.assertIn('could not finish', diagnostics[0])
        diagnostics = []
        await supported_items([item], [protein_source()], {}, AsyncMock(return_value={'checks':[
            {'id':'p','supported':False,'reason':'Different organism'}]}), diagnostics)
        self.assertIn('Different organism', diagnostics[0])

    async def test_reviews_are_bounded_without_truncating_source_quotes(self):
        source = protein_source().model_copy(update={'quote':'x' * 1000 + 'critical qualifier'})
        items = [{'id':str(i),'text':'Interpretation','evidence_refs':['e1']} for i in range(5)]
        generate = AsyncMock(return_value={'checks':[]})
        await supported_items(items, [source], {}, generate)
        self.assertEqual(generate.await_count, 3)
        self.assertTrue(all('critical qualifier' in call.args[0] for call in generate.await_args_list))

    async def test_reported_mammalian_paper_cannot_generate_itaconic_recommendation(self):
        generate = AsyncMock()
        state = {'query':'Choose a first experiment', 'selected_project':{'end_product':'Itaconic acid produced from glucose'}}
        self.assertFalse(relevant_evidence(state, [protein_source()]))
        with self.assertRaisesRegex(ValueError, 'No verified passages match'):
            await generate_board(workspace_key='test', state=state, evidence=[protein_source()], generate=generate)
        generate.assert_not_called()

    async def test_two_excerpts_do_not_become_two_papers_even_if_auditor_would_approve(self):
        source = protein_source()
        other = source.model_copy(update={'id':'e2','page':4})
        generate = AsyncMock(return_value={'checks':[{'id':'p','supported':True,'reason':'incorrect approval'}]})
        accepted = await supported_items([{'id':'p','text':'Supported by multiple experimental papers.', 'evidence_refs':['e1','e2']}], [source,other], {}, generate)
        self.assertFalse(accepted)
        generate.assert_not_called()

    async def test_invented_local_experience_is_rejected_before_model_audit(self):
        self.assertTrue(structural_problem('Given the local experience, our laboratory has the necessary expertise.', ['e1'], [protein_source()], {}))
        self.assertFalse(structural_problem('Is this equipment available in your laboratory?', ['e1'], [protein_source()], {}))

    async def test_failed_or_incomplete_audit_cannot_license_output(self):
        item = {'id':'p','text':'A proposed interpretation', 'evidence_refs':['e1']}
        for response in [{}, {'checks':[{'id':'p','supported':True}]}]:
            self.assertFalse(await supported_items([item], [protein_source()], {}, AsyncMock(return_value=response)))
        self.assertFalse(await supported_items([item], [protein_source()], {}, AsyncMock(side_effect=RuntimeError('offline'))))

    async def test_only_explicit_supported_audit_entries_are_accepted(self):
        items = [{'id':name,'text':'Interpretation','evidence_refs':['e1']} for name in ['supported','unsupported']]
        generate = AsyncMock(return_value={'checks':[{'id':'supported','supported':True,'reason':'Supported by cited experiment'}, {'id':'unsupported','supported':False,'reason':'Different outcome'}]})
        self.assertEqual(await supported_items(items,[protein_source()],{},generate), {'supported'})

    async def test_unrelated_legacy_citation_and_caption_are_not_topic_evidence(self):
        state={'selected_project':{'end_product':'itaconic acid'}}
        self.assertFalse(relevant_evidence(state,[protein_source()]))
        relevant=protein_source().model_copy(update={'document_context':'Production of itaconic acid by engineered yeast.'})
        self.assertEqual(relevant_evidence(state,[relevant]),[relevant])

    async def test_legacy_rules_are_not_injected_and_api_requires_regeneration(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from research_board import BoardRepository, ResearchBoard, confirmed_rule_context
        from research_board_api import board_router
        legacy = ResearchBoard(workspace_key='old', decision_key='d', query='Choose')
        self.assertEqual(confirmed_rule_context(legacy), [])
        with tempfile.TemporaryDirectory() as folder:
            db = SimpleNamespace(db_path=str(Path(folder)/'test.sqlite'))
            BoardRepository(db.db_path).save(legacy, 0)
            app=FastAPI(); app.include_router(board_router(db, SimpleNamespace(model='test')))
            with TestClient(app) as client:
                response=client.post('/api/research-board/answer',json={'workspace_key':'old','expected_revision':1,'question_id':'old-question','answer_type':'allow'})
                self.assertEqual(response.status_code,409)
                self.assertIn('Refresh the evidence',response.json()['detail'])
