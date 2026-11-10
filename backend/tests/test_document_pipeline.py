import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from document_pipeline import (accept_classification, classify_passages, passages_from_pages,
                               parse_document, source_notes)


def fixture():
    return passages_from_pages([{'page_num': 1, 'blocks': [
        {'kind': 'heading', 'text': 'Results'},
        {'kind': 'paragraph', 'text': 'Strain A produced 5 g/L after 48 hours.', 'bbox': {'x': 1, 'y': 2, 'width': 10, 'height': 5}},
    ]}], 'hash')[1:]


class DocumentTests(unittest.IsolatedAsyncioTestCase):
    async def test_selection_distinguishes_rejection_from_model_failure(self):
        from research_tools import _llm_refine_annotation_candidates
        candidate = {'candidate_id':'stable-id', 'page':1, 'snippet':'Reported source result.'}
        async def select():
            return await _llm_refine_annotation_candidates(candidates=[candidate], contexts={}, max_annotations=3)
        with patch.dict('os.environ', {'DISABLE_PDF_ANNOTATION_LLM':'0'}), \
             patch('ollama_client.ollama.generate_json', AsyncMock(return_value={'selected':[]})) as generate:
            self.assertEqual(await select(), [])
            self.assertEqual(generate.await_args.kwargs['num_ctx'], 16384)
            generate.return_value = {'selected':[{'candidate_id':'c1'}]}
            self.assertEqual((await select())[0]['candidate_id'], 'stable-id')
            generate.return_value = {'selected':[{'candidate_id':'unknown'}]}
            with self.assertRaisesRegex(RuntimeError, 'unknown passage'):
                await select()
            generate.side_effect = TimeoutError()
            with self.assertRaisesRegex(RuntimeError, 'could not finish'):
                await select()

    async def test_strict_parser_defaults_to_cached_local_parsing(self):
        from scientific_pdf_parsing import parse_scientific_pdf
        with patch.dict('os.environ', {'DOCLING_ENABLED':'0', 'DOCLING_URL':'', 'GROBID_URL':''}), \
             patch('document_pipeline.parse_document', AsyncMock(return_value={'passages':fixture()})):
            result = await parse_scientific_pdf('paper.pdf')
        self.assertEqual(result['parsers'], ['liteparse'])
        self.assertIn('Strain A', result['text_excerpt'])

    async def test_short_model_ids_resolve_to_stable_source_ids(self):
        p = fixture()
        model = AsyncMock(return_value={'passages':[{'id':'p1','labels':['result'],'facts':[]}]})
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DOCUMENT_CACHE_ROOT':folder}):
            rows = await classify_passages({'identity':{},'passages':p}, 'paper.pdf', model, 'test')
        self.assertEqual(rows[0]['id'], p[0]['id'])
        self.assertEqual(rows[0]['classification_status'], 'complete')

    def test_stable_passages_keep_coordinates_and_table_headers(self):
        self.assertEqual(fixture(), fixture())
        self.assertEqual(fixture()[0]['section'], 'Results')
        self.assertEqual(fixture()[0]['bbox']['x'], 1)
        table = passages_from_pages([{'page_num': 2, 'blocks': [{'kind': 'table',
            'header': [{'text':'Strain'}, {'text':'Titer'}],
            'rows': [[{'text':'A'}, {'text':'5 g/L'}]]}]}], 'hash')
        self.assertEqual(table[0]['text'], 'Strain | Titer A | 5 g/L')

    def test_only_exact_facts_and_valid_categories_are_accepted(self):
        p = fixture()
        rows = accept_classification(p, {'passages':[{'id':p[0]['id'], 'labels':['result','made-up'],
            'facts':[{'kind':'evidence_claims','value':'produced 5 g/L'},
                     {'kind':'evidence_claims','value':'produced 50 g/L'}]}]})
        self.assertEqual(rows[0]['labels'], ['result'])
        self.assertEqual(len(rows[0]['facts']), 1)
        self.assertEqual(source_notes(rows)['evidence_claims'], ['Page 1: produced 5 g/L'])
        rows[0]['labels'] = ['background']
        self.assertFalse(source_notes(rows)['evidence_claims'])

    async def test_source_only_cache_reused_and_model_change_invalidates(self):
        passages = fixture()
        generate = AsyncMock(return_value={'passages':[{'id':passages[0]['id'], 'labels':['result'], 'facts':[]}]})
        document = {'identity':{'source_sha256':'hash'}, 'passages':passages}
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DOCUMENT_CACHE_ROOT':folder}):
            await classify_passages(document, 'paper.pdf', generate, 'model-a')
            await classify_passages(document, 'another-project/paper.pdf', generate, 'model-a')
            self.assertEqual(generate.await_count, 1)
            await classify_passages(document, 'paper.pdf', generate, 'model-b')
            self.assertEqual(generate.await_count, 2)
        self.assertNotIn('selected_project', generate.await_args.args[0])

    async def test_failed_classification_is_not_cached_as_empty_success(self):
        document = {'identity':{}, 'passages':fixture()}
        generate = AsyncMock(return_value={})
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DOCUMENT_CACHE_ROOT':folder}):
            result = await classify_passages(document, 'paper.pdf', generate, 'model')
            self.assertEqual(result[0]['classification_status'], 'unavailable')
            self.assertFalse(list(Path(folder).glob('classify-*')))

    async def test_parser_reuses_hash_and_invalidates_changed_bytes(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DOCUMENT_CACHE_ROOT':folder}):
            path = Path(folder)/'paper.pdf'
            with fitz.open() as doc:
                doc.new_page().insert_text((50,50), 'Results: Strain A produced 5 g/L.')
                doc.save(path)
            first = await parse_document(path)
            self.assertFalse(first['cache_hit'])
            with patch('document_pipeline.asyncio.create_subprocess_exec') as process:
                second = await parse_document(path)
                process.assert_not_called()
            self.assertTrue(second['cache_hit'])
            path.write_bytes(path.read_bytes() + b'\n% modified\n')
            third = await parse_document(path)
            self.assertNotEqual(first['identity']['source_sha256'], third['identity']['source_sha256'])

    async def test_cancelled_parser_is_killed_and_temp_file_removed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DOCUMENT_CACHE_ROOT':folder}):
            path = Path(folder)/'paper.pdf'; path.write_bytes(b'%PDF-1.7')
            from unittest.mock import Mock
            process = Mock(returncode=None)
            process.communicate = AsyncMock(side_effect=asyncio.CancelledError())
            process.wait = AsyncMock()
            with patch('document_pipeline.asyncio.create_subprocess_exec', AsyncMock(return_value=process)):
                with self.assertRaises(asyncio.CancelledError):
                    await parse_document(path)
            process.kill.assert_called_once()
            process.wait.assert_awaited_once()
            self.assertEqual(list(Path(folder).glob('*.json')), [])
