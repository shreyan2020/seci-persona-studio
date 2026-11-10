"""Reproducible synthetic benchmark; no model calls or project data changes."""
import hashlib
import json
from pathlib import Path
import re
import statistics
import tempfile
import time

import fitz
from research_board import normalized_text, verified_pdf_evidence


def baseline(state, root):
    """Previous strategy: hash originals, reopen and scan references per quote."""
    paths = {hashlib.sha256(p.read_bytes()).hexdigest(): p
             for p in root.glob('*/*/original.pdf')}
    accepted = []
    for finding in state['research_work_template']['literature_findings']:
        for annotation in finding['annotations']:
            with fitz.open(paths[annotation['source_sha256']]) as doc:
                references = next((i + 1 for i, page in enumerate(doc)
                                   if re.search(r'(?im)^\s*references\s*$', page.get_text())), len(doc) + 1)
                number = annotation['page']
                if number < references and normalized_text(annotation['snippet']) in normalized_text(doc[number - 1].get_text()):
                    accepted.append((number, annotation['snippet']))
    return accepted


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pdf = root / 'project' / 'paper' / 'original.pdf'
        pdf.parent.mkdir(parents=True)
        with fitz.open() as doc:
            for i in range(40):
                doc.new_page().insert_text((40, 40), f'Experimental condition {i + 1} increased measured yield.')
            doc.new_page().insert_text((40, 40), 'References\nOther study.')
            doc.save(pdf)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        annotations = [dict(page=i + 1, snippet=f'Experimental condition {i + 1} increased measured yield.',
                            evidence_kind='pdf_passage', source_sha256=digest) for i in range(20)]
        state = {'research_work_template': {'literature_findings': [dict(citation='Synthetic benchmark', annotations=annotations)]}}
        expected = baseline(state, root)
        actual = [(e.page, e.quote) for e in verified_pdf_evidence(state, root)]
        assert actual == expected, 'Output changed'
        timings = {}
        for name, function in [('previous', baseline), ('optimized', verified_pdf_evidence)]:
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                function(state, root)
                samples.append((time.perf_counter() - start) * 1000)
            timings[name] = round(statistics.median(samples), 3)
        print(json.dumps({'fixture_pages': 41, 'passages': 20, 'runs': 7,
                          'median_ms': timings, 'speedup': round(timings['previous'] / timings['optimized'], 2),
                          'same_evidence': True}, indent=2))


if __name__ == '__main__':
    main()
