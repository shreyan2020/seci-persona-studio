import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from research_tools import download_open_access_pdf
from models import ResearchFinding


class PaperReuseTests(unittest.TestCase):
    def test_saved_original_skips_network_and_identifier_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'PMID123' / 'original.pdf'
            path.parent.mkdir()
            path.write_bytes(b'%PDF-1.7\ncontrolled cache fixture')
            with patch('research_tools.httpx.AsyncClient') as client, patch('research_tools.resolve_pmcid_from_pmid', new_callable=AsyncMock) as resolve:
                result = asyncio.run(download_open_access_pdf(pmid='123', pdf_url='https://example.org/paper.pdf', output_dir=folder))
            self.assertTrue(result['cache_hit'])
            client.assert_not_called()
            resolve.assert_not_awaited()
            self.assertEqual(Path(result['original_pdf_path']), path)

    def test_resolved_pmc_original_skips_download(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'PMC123' / 'original.pdf'
            path.parent.mkdir()
            path.write_bytes(b'%PDF-1.7\ncontrolled cache fixture')
            with patch('research_tools.httpx.AsyncClient') as client, patch('research_tools.resolve_pmcid_from_pmid', new_callable=AsyncMock, return_value='PMC123'):
                result = asyncio.run(download_open_access_pdf(pmid='123', output_dir=folder))
            self.assertTrue(result['cache_hit'])
            client.assert_not_called()

    def test_non_pdf_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'paper' / 'original.pdf'
            path.parent.mkdir()
            path.write_text('<html>download failed</html>')
            result = asyncio.run(download_open_access_pdf(output_dir=folder))
            self.assertEqual(result['status'], 'not_open_access')

    def test_reader_location_survives_workspace_serialization(self):
        saved = {'context_key': 'scoped-query', 'url': '/api/projects/1/literature/pdf/PMC1/annotated', 'path': 'annotated.pdf'}
        finding = ResearchFinding(id='paper', pdf_reader=saved)
        self.assertEqual(ResearchFinding.model_validate_json(finding.model_dump_json()).pdf_reader, saved)
