"""Resolve article PDFs from NLM's public, versioned PMC Cloud metadata."""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

BASE = 'https://pmc-oa-opendata.s3.amazonaws.com'


async def pdf_locations(client, pmcid):
    if not re.fullmatch(r'PMC\d+', pmcid):
        return []
    response = await client.get(BASE + '/', params={
        'list-type': '2', 'prefix': pmcid + '.', 'delimiter': '/', 'max-keys': 100,
    })
    response.raise_for_status()
    root = ET.fromstring(response.content)
    prefixes = [e.text for e in root.findall('.//{*}CommonPrefixes/{*}Prefix')
                if e.text and re.fullmatch(re.escape(pmcid) + r'\.\d+/', e.text)]
    locations = []
    for prefix in prefixes[:10]:
        response = await client.get(f'{BASE}/{prefix}{prefix[:-1]}.json')
        response.raise_for_status()
        metadata = response.json()
        url = str(metadata.get('pdf_url') or '')
        parsed = urlparse(url)
        if parsed.scheme == 's3' and parsed.netloc == 'pmc-oa-opendata':
            url = BASE + parsed.path + ('?' + parsed.query if parsed.query else '')
            parsed = urlparse(url)
        if parsed.scheme == 'https' and parsed.netloc == 'pmc-oa-opendata.s3.amazonaws.com' and parsed.path.startswith('/' + prefix):
            locations.append((metadata.get('is_manuscript') in (True, 'yes'), url))
    # Prefer the published article, not an arbitrarily higher version number.
    return [url for _, url in sorted(locations, key=lambda item: item[0])]
