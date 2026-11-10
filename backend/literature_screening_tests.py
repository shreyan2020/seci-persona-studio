import unittest
from unittest.mock import AsyncMock, patch
from research_tools import (_literature_relevance_profile, _screen_literature_record,
                            _llm_refine_literature_records, search_literature)

QUERY = 'For glucose-based itaconic acid production in Yarrowia lipolytica, modify the pathway or cultivation conditions?'


class ScreeningTests(unittest.IsolatedAsyncioTestCase):
    def profile(self):
        return _literature_relevance_profile(QUERY, end_product='Itaconic acid produced from glucose', target_host='Yarrowia lipolytica')

    def test_generic_match_and_supplement_are_excluded(self):
        profile = self.profile()
        self.assertEqual(profile['target_product_terms'], ['itaconic', 'acid'])
        self.assertNotIn('for', profile['terms'])
        self.assertNotIn('production', profile['terms'])
        self.assertFalse(_screen_literature_record({'title': 'Secretion and uptake of TAT-fusion proteins produced by engineered mammalian cells'}, profile)['eligible'])
        self.assertFalse(_screen_literature_record({'title': 'Itaconic acid in Yarrowia lipolytica', 'doi': '10.1234/example.s001'}, profile)['eligible'])

    def test_host_transfer_is_explicit_and_not_direct_evidence(self):
        direct = _screen_literature_record({'title': 'Itaconic acid production from glucose in Yarrowia lipolytica'}, self.profile())
        transfer = _screen_literature_record({'title': 'Itaconic acid production in Aspergillus terreus'}, self.profile())
        self.assertEqual(direct['scope'], 'host/product match')
        self.assertEqual(transfer['scope'], 'transfer candidate')

    async def test_negative_model_rationale_is_not_selected(self):
        with patch('ollama_client.ollama.generate_json', new=AsyncMock(return_value={'selected': [{'candidate_id': 'cand_1', 'relevant': True, 'rationale': 'This record is not relevant to the project goal.', 'evidence_role': 'background'}]})):
            result = await _llm_refine_literature_records(candidates=[{'title': 'Itaconic acid'}], query=QUERY)
        self.assertEqual(result, [])

    async def test_exclusion_is_not_refilled_and_queries_keep_product(self):
        direct = {'title': 'Itaconic acid in Yarrowia lipolytica', 'doi': '10.1234/direct'}
        unrelated = {'title': 'TAT proteins produced in mammalian cells', 'doi': '10.1234/tat'}
        with patch('research_tools.search_pubmed', new=AsyncMock(return_value={'results': [direct, unrelated]})) as pubmed, \
             patch('research_tools.search_semantic_scholar', new=AsyncMock(return_value={})), \
             patch('research_tools.search_openalex', new=AsyncMock(return_value={})), \
             patch('research_tools.search_crossref', new=AsyncMock(return_value={})), \
             patch('research_tools._llm_refine_literature_records', new=AsyncMock(return_value=[])) as selector:
            result = await search_literature(QUERY, end_product='Itaconic acid produced from glucose', target_host='Yarrowia lipolytica')
        self.assertEqual(result['results'], [])
        self.assertEqual(len(result['screening_rejections']), 1)
        self.assertEqual(len(selector.call_args.kwargs['candidates']), 1)
        for query in pubmed.call_args.kwargs['anchored_queries']:
            self.assertIn('itaconic acid', query)

    async def test_model_failure_fallback_contains_only_screened_records(self):
        with patch('research_tools.search_pubmed', new=AsyncMock(return_value={'results': [{'title': 'Itaconic acid in Yarrowia lipolytica', 'doi': '10.1234/direct'}, {'title': 'Mammalian protein production', 'doi': '10.1234/wrong'}]})), \
             patch('research_tools.search_semantic_scholar', new=AsyncMock(return_value={})), \
             patch('research_tools.search_openalex', new=AsyncMock(return_value={})), \
             patch('research_tools.search_crossref', new=AsyncMock(return_value={})), \
             patch('research_tools._llm_refine_literature_records', new=AsyncMock(return_value=None)):
            result = await search_literature(QUERY, end_product='Itaconic acid', target_host='Yarrowia lipolytica')
        self.assertEqual([r['doi'] for r in result['results']], ['10.1234/direct'])
