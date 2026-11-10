import asyncio
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pmc_cloud import BASE, pdf_locations
from research_tools import download_open_access_pdf


class CloudTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_real_metadata_shape_and_prefers_published_version(self):
        async def handler(request):
            if request.url.path == '/':
                return httpx.Response(200, text='<ListBucketResult xmlns="urn:s3"><CommonPrefixes><Prefix>PMC123.2/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>PMC123.3/</Prefix></CommonPrefixes></ListBucketResult>')
            version = request.url.path.split('/')[1]
            return httpx.Response(200, json={'is_manuscript': version.endswith('.3'),
                'pdf_url': f's3://pmc-oa-opendata/{version}/article.pdf?md5=example'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            urls = await pdf_locations(client, 'PMC123')
        self.assertEqual(urls[0], BASE + '/PMC123.2/article.pdf?md5=example')
        self.assertEqual(len(urls), 2)

    async def test_metadata_cannot_redirect_to_another_article_or_host(self):
        for url in ['https://example.com/paper.pdf', BASE + '/PMC999.1/paper.pdf']:
            async def handler(request):
                if request.url.path == '/':
                    return httpx.Response(200, text='<r><CommonPrefixes><Prefix>PMC123.1/</Prefix></CommonPrefixes></r>')
                return httpx.Response(200, json={'pdf_url': url})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                self.assertEqual(await pdf_locations(client, 'PMC123'), [])

    async def test_challenge_with_pdf_content_type_is_not_saved(self):
        async def handler(request):
            return httpx.Response(200, text='<html>challenge</html>', headers={'content-type':'application/pdf'})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with tempfile.TemporaryDirectory() as folder, patch('research_tools.httpx.AsyncClient', return_value=client):
            result = await download_open_access_pdf(pdf_url='https://example.com/paper.pdf', output_dir=folder)
            from pathlib import Path
            self.assertFalse(list(Path(folder).rglob('original.pdf')))
            self.assertNotEqual(result['status'], 'success')
