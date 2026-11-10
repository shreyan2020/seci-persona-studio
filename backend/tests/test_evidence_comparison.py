import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from research_board import ResearchBoard, BoardEvidence, BoardAction, BoardRepository, review_rule, generate_board
from evidence_comparison import accept_cells, accept_facts, accept_links, guided_judgment, build_comparison
from research_board_api import board_router


def fixture():
    b = ResearchBoard(grounding_version=2, workspace_key='test', decision_key='test', query='Choose the next experiment',
        evidence=[BoardEvidence(id='e1', source_id='paper1', citation='Controlled fixture',page=1,source_sha256='hash',
            quote='The strain in shake flasks produced 10 mg/L. Its comparator produced 5 mg/L.')],
        actions=[BoardAction(id='a1',label='Test intervention',evidence_refs=['e1'])])
    b.comparison_rows = accept_cells(b, {'rows':[{'evidence_id':'e1','cells':{'cultivation':'shake flasks','titer':'10 mg/L'}}]}, {'e1'})
    return b


class ComparisonTests(unittest.TestCase):
    def test_researcher_detail_stays_attached_and_persists(self):
        b=fixture()
        b.experiment_facts=accept_facts(b,{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'shake flasks'}]}, {'e1'})
        f=b.experiment_facts[0];f.review='confirmed'
        result=guided_judgment(b,row_id=f.id,dimension=f.dimension,relation='different',basis='setup',detail='Our reactor uses manual feeding.')
        with tempfile.TemporaryDirectory() as path:
            repo=BoardRepository(str(Path(path)/'board.db'));repo.save(result,0)
            saved=repo.get(b.workspace_key)
            self.assertEqual(saved.comparison_judgments[0].row_id,f.id)
            self.assertEqual(saved.comparison_judgments[0].detail,'Our reactor uses manual feeding.')
            self.assertFalse(saved.rules)
            changed=guided_judgment(saved,row_id=f.id,dimension=f.dimension,relation='different',basis='setup',detail='We now use an automatic feed pump.')
            self.assertEqual(len(changed.comparison_judgments),2)

    def test_unquoted_values_unknown_ids_and_unitless_numbers_are_dropped(self):
        b=fixture()
        rows=accept_cells(b,{'rows':[{'evidence_id':'invented','cells':{'cultivation':'shake flasks'}},
            {'evidence_id':'e1','cells':{'host':'Yarrowia lipolytica','titer':'10','comparator':'5 mg/L'}}]}, {'e1'})
        self.assertEqual(list(rows[0].cells),['comparator'])

    def test_extraction_never_combines_passages(self):
        b=fixture()
        b.evidence.append(BoardEvidence(id='e2',source_id='paper1',citation='Fixture',page=2,source_sha256='hash',quote='Bioreactor production reached 200 mg/L.'))
        rows=accept_cells(b,{'rows':[{'evidence_id':'e1','cells':{'cultivation':'shake flasks','titer':'200 mg/L'}}]}, {'e1','e2'})
        self.assertNotIn('titer',rows[0].cells)

    def test_source_review_required_and_unknown_does_not_make_rule(self):
        b=fixture();rid=b.comparison_rows[0].id
        with self.assertRaises(ValueError): guided_judgment(b,row_id=rid,dimension='cultivation',relation='same',basis='setup')
        b.comparison_rows[0].cells['cultivation'].review='confirmed'
        with self.assertRaises(ValueError): guided_judgment(b,row_id=rid,dimension='cultivation',relation='unknown',basis='uncertain',consequence='avoid',action_ids=['a1'])
        result=guided_judgment(b,row_id=rid,dimension='cultivation',relation='unknown',basis='uncertain',consequence='measure')
        self.assertFalse(result.rules)
        self.assertEqual(result.resolution_steps[-1]['resolver'],'run_experiment')

    def test_past_case_choices_create_draft_and_preserve_exception(self):
        b=fixture();b.comparison_rows[0].cells['cultivation'].review='confirmed'
        kwargs=dict(row_id=b.comparison_rows[0].id,dimension='cultivation',relation='different',basis='past_case',cue='growth',response='conditions',exception='equipment',consequence='avoid',action_ids=['a1'])
        result=guided_judgment(b,**kwargs)
        self.assertEqual(result.actions[0].disposition,'eligible')
        self.assertIn('Revisit when equipment is available',result.rules[0].statement)
        self.assertEqual(len(guided_judgment(result,**kwargs).rules),1)
        confirmed=review_rule(result,result.rules[0].id,'confirm')
        self.assertEqual(confirmed.actions[0].disposition,'excluded')
        self.assertEqual(review_rule(confirmed,result.rules[0].id,'revoke').actions[0].disposition,'eligible')

    def test_api_persists_review_choice_and_rejects_stale_request(self):
        with tempfile.TemporaryDirectory() as temp:
            db=SimpleNamespace(db_path=str(Path(temp)/'test.sqlite'))
            b=BoardRepository(db.db_path).save(fixture(),0)
            app=FastAPI();app.include_router(board_router(db,SimpleNamespace(model='test')))
            client=TestClient(app)
            payload={'workspace_key':'test','expected_revision':1,'row_id':b.comparison_rows[0].id,'dimension':'cultivation','review':'confirmed'}
            self.assertEqual(client.post('/api/research-board/compare-choice',json=payload).status_code,200)
            self.assertEqual(client.post('/api/research-board/compare-choice',json=payload).status_code,409)
            payload.update(expected_revision=2,review=None,relation='same',basis='setup')
            response=client.post('/api/research-board/compare-choice',json=payload)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(BoardRepository(db.db_path).get('test').comparison_judgments),1)

    def test_external_search_uses_topic_not_private_account(self):
        with tempfile.TemporaryDirectory() as temp:
            db=SimpleNamespace(db_path=str(Path(temp)/'test.sqlite'));b=fixture()
            b.comparison_project={'end_product':'Itaconic acid','target_host':'Yarrowia lipolytica','project_goal':'PRIVATE lab account'}
            BoardRepository(db.db_path).save(b,0)
            app=FastAPI();app.include_router(board_router(db,SimpleNamespace(model='test')))
            with patch('research_board_api.search_literature',new=AsyncMock(return_value={'results':[],'errors':{}})) as search:
                response=TestClient(app).post('/api/research-board/gap-sources',json={'workspace_key':'test','expected_revision':1,'dimension':'cultivation'})
            self.assertEqual(response.status_code,200)
            self.assertNotIn('PRIVATE',str(search.call_args))
            self.assertEqual(search.call_args.kwargs['search_focus'],'Cultivation')

    def test_rejecting_source_detail_withdraws_dependent_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            db=SimpleNamespace(db_path=str(Path(temp)/'test.sqlite'));b=fixture()
            row=b.comparison_rows[0];row.cells['cultivation'].review='confirmed'
            b=guided_judgment(b,row_id=row.id,dimension='cultivation',relation='unavailable',basis='setup',consequence='avoid',action_ids=['a1'])
            b=review_rule(b,b.rules[0].id,'confirm')
            BoardRepository(db.db_path).save(b,0)
            app=FastAPI();app.include_router(board_router(db,SimpleNamespace(model='test')))
            response=TestClient(app).post('/api/research-board/compare-choice',json={'workspace_key':'test','expected_revision':1,'row_id':row.id,'dimension':'cultivation','review':'rejected'})
            self.assertEqual(response.status_code,200)
            state=response.json()['board']
            self.assertEqual(state['rules'][0]['status'],'revoked')
            self.assertEqual(state['actions'][0]['disposition'],'eligible')

    def test_rejecting_experiment_fact_removes_it_from_record(self):
        with tempfile.TemporaryDirectory() as temp:
            db=SimpleNamespace(db_path=str(Path(temp)/'test.sqlite'));b=fixture()
            b.experiment_facts=accept_facts(b,{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'shake flasks'}]},{'e1'})
            fact=b.experiment_facts[0]
            b.experiment_records=accept_links(b,{'experiments':[{'title':'Flask setting','fact_ids':[fact.id]}]})
            BoardRepository(db.db_path).save(b,0)
            app=FastAPI();app.include_router(board_router(db,SimpleNamespace(model='test')))
            response=TestClient(app).post('/api/research-board/compare-choice',json={'workspace_key':'test','expected_revision':1,'row_id':fact.id,'dimension':'cultivation','review':'rejected'})
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['board']['experiment_records'])

    def test_identical_refresh_preserves_review_but_changed_span_does_not(self):
        b=fixture();b.experiment_facts=accept_facts(b,{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'shake flasks'}]}, {'e1'})
        b.experiment_facts[0].review='confirmed'
        generate=AsyncMock(side_effect=[{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'shake flasks'}]},
                                        {'experiments':[{'title':'Flask experiment','fact_ids':[b.experiment_facts[0].id]}]}])
        same=asyncio.run(build_comparison(b,b.evidence,generate))
        self.assertEqual(same.experiment_facts[0].review,'confirmed')
        generate=AsyncMock(side_effect=[{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'The strain in shake flasks'}]},
                                        {'experiments':[]}])
        changed=asyncio.run(build_comparison(b,b.evidence,generate))
        self.assertEqual(changed.experiment_facts[0].review,'unreviewed')

    def test_cross_passage_link_requires_same_explicit_anchor(self):
        b=fixture();b.evidence.append(BoardEvidence(id='e2',source_id='paper1',citation='Fixture',page=2,source_sha256='hash',quote='Strain S10 reached 20 mg/L in the reported test.'))
        b.evidence[0].quote='Strain S10 was cultivated in shake flasks.'
        b.experiment_facts=accept_facts(b,{'facts':[
            {'evidence_id':'e1','dimension':'cultivation','value':'shake flasks','anchors':[{'kind':'strain','value':'Strain S10'}]},
            {'evidence_id':'e2','dimension':'titer','value':'20 mg/L','anchors':[{'kind':'strain','value':'Strain S10'}]},
        ]},{'e1','e2'})
        proposal={'experiments':[{'title':'S10 flask test','fact_ids':[f.id for f in b.experiment_facts],'link_anchor':{'kind':'strain','value':'Strain S10'}}]}
        records=accept_links(b,proposal)
        self.assertEqual(len(records),1);self.assertEqual(records[0].link_status,'linked')
        proposal['experiments'][0]['link_anchor']['value']='another strain'
        self.assertTrue(all(r.link_status=='unresolved' for r in accept_links(b,proposal)))

    def test_different_cultivation_and_carbon_sources_stay_separate(self):
        b=fixture();b.evidence[0].quote='Condition A used glucose in shake flasks and glycerol in a bioreactor.'
        b.experiment_facts=accept_facts(b,{'facts':[
            {'evidence_id':'e1','dimension':'carbon_source','value':'glucose'},
            {'evidence_id':'e1','dimension':'carbon_source','value':'glycerol'},
            {'evidence_id':'e1','dimension':'cultivation','value':'shake flasks'},
            {'evidence_id':'e1','dimension':'cultivation','value':'bioreactor'},
        ]},{'e1'})
        records=accept_links(b,{'experiments':[{'title':'Invalid merge','fact_ids':[f.id for f in b.experiment_facts]}]})
        self.assertEqual(len(records),4)
        self.assertTrue(all(r.link_status=='unresolved' for r in records))
        glucose=next(f for f in b.experiment_facts if f.value=='glucose')
        glycerol=next(f for f in b.experiment_facts if f.value=='glycerol')
        self.assertIn('CHEBI:17234',[t.term_id for t in glucose.ontology_terms])
        self.assertIn('CHEBI:17754',[t.term_id for t in glycerol.ontology_terms])

    def test_fed_batch_setting_is_not_automatically_an_intervention(self):
        b=fixture();b.evidence[0].quote='The strain was grown by fed-batch cultivation.'
        b.experiment_facts=accept_facts(b,{'facts':[{'evidence_id':'e1','dimension':'cultivation','value':'fed-batch cultivation','intervention_type':'process'}]},{'e1'})
        self.assertEqual(b.experiment_facts[0].intervention_type,'none')
        record=accept_links(b,{'experiments':[{'title':'Fed-batch setting','fact_ids':[b.experiment_facts[0].id]}]})[0]
        self.assertEqual(record.category,'cultivation')

    def test_extraction_prompt_warns_that_comparator_is_not_causal_proof(self):
        b=fixture();generate=AsyncMock(side_effect=[{'facts':[]},{'experiments':[]}])
        asyncio.run(build_comparison(b,b.evidence,generate))
        self.assertIn('not proof that one intervention caused',generate.await_args_list[0].args[0])
