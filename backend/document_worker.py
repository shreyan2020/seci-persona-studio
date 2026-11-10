"""Isolated local parser process. No network inference or project context."""
import dataclasses
import json
import sys
from liteparse import LiteParse


def parse(path):
    with LiteParse(ocr_enabled=True, ocr_failure_fatal=True, extract_blocks=True,
                   extract_links=False, quiet=True, max_pages=300) as parser:
        result = parser.parse(path)
        if result.total_pages != len(result.pages):
            raise ValueError('Document was not completely parsed')
        return {'pages': [dataclasses.asdict(page) for page in result.pages],
                'total_pages': result.total_pages}


if __name__ == '__main__':
    with open(sys.argv[2], 'w', encoding='utf-8') as output:
        json.dump(parse(sys.argv[1]), output, ensure_ascii=False)
