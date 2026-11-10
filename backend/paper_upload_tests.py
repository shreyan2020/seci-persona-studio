import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from paper_upload import paper_upload_router


class UploadTests(unittest.TestCase):
    def test_upload_stores_pdf_by_hash_and_invalid_upload_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = FastAPI(); app.include_router(paper_upload_router(lambda pid: {'id':pid} if pid==4 else None))
            with fitz.open() as document:
                document.new_page().insert_text((50,50),'A real PDF fixture')
                content = document.tobytes()
            with patch('paper_upload.paper_evidence_root', return_value=root), TestClient(app) as client:
                result = client.post('/api/projects/4/literature/upload',files={'file':('../../wrong.pdf',content,'application/pdf')})
                self.assertEqual(result.status_code,200)
                paper_id=result.json()['paper_id']
                self.assertEqual((root/'project_4'/paper_id/'original.pdf').read_bytes(),content)
                bad=client.post('/api/projects/4/literature/upload',files={'file':('fake.pdf',b'not a PDF','application/pdf')})
                self.assertEqual(bad.status_code,422)
                self.assertEqual(list((root/'project_4').glob('*.pdf')),[])
                self.assertEqual(client.post('/api/projects/99/literature/upload',files={'file':('test.pdf',content)}).status_code,404)
