"""Europe PMC search, resolution and validated downloads (no API credentials)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from literature_kit.papers import PaperError, doi_value, save_exclusive


def normalize(record):
    year = record.get('pubYear')
    links = (record.get('fullTextUrlList') or {}).get('fullTextUrl') or []
    return dict(id=record.get('id'), source=record.get('source'), pmcid=record.get('pmcid'),
                title=record.get('title'), abstract=record.get('abstractText'),
                year=int(year) if str(year).isdigit() else None,
                authors=[a.get('fullName') or a.get('collectiveName')
                         for a in ((record.get('authorList') or {}).get('author') or [])],
                doi=record.get('doi'), url=f"https://europepmc.org/article/{record.get('source')}/{record.get('id')}",
                pdf_url=next((x.get('url') for x in links if x.get('documentStyle') == 'pdf'), None),
                full_text_links=links, citation_count=record.get('citedByCount'),
                is_open_access=record.get('isOpenAccess'), has_supplements=record.get('hasSuppl'))


def search(client, query, limit, filter_value=None):
    if filter_value:
        raise PaperError('Use Europe PMC native field syntax in --query, not --filter')
    records, cursor = [], '*'
    seen = set()
    while len(records) < limit:
        data = client._fetch('/search', {'query': query, 'format': 'json', 'resultType': 'core',
                                        'pageSize': min(100, limit-len(records)), 'cursorMark': cursor})
        batch = (data.get('resultList') or {}).get('result') or []
        records.extend(batch[:limit-len(records)])
        next_cursor = data.get('nextCursorMark')
        if not batch or len(records) >= data.get('hitCount', 0) or not next_cursor or next_cursor in seen:
            break
        seen.add(cursor)
        cursor = next_cursor
    return client._result('search', query, records)


def lookup(client, identifier):
    value = identifier.strip()
    pmc = value.upper().removeprefix('PMCID:')
    if re.fullmatch(r'PMC\d+', pmc):
        query = 'PMCID:' + pmc
    elif value.upper().startswith('PMID:') or value.isdigit():
        pmid = value.split(':', 1)[-1]
        if not pmid.isdigit():
            raise PaperError('PMID must be numeric')
        query = 'EXT_ID:' + pmid + ' AND SRC:MED'
    else:
        doi = doi_value(value)
        if not re.fullmatch(r'10\.\d{4,9}/[^\s"\\]+', doi):
            raise PaperError('Use a DOI, PMID:number, numeric PMID, PMCnumber or PMCID:PMCnumber')
        query = 'DOI:"' + doi + '"'
    data = client._fetch('/search', {'query': query, 'format': 'json', 'resultType': 'core', 'pageSize': 2})
    records = (data.get('resultList') or {}).get('result') or []
    count = data.get('hitCount', len(records))
    if count != 1 or len(records) != 1:
        raise PaperError('No unique Europe PMC match; use an exact PMID or PMCID')
    record = records[0]
    if query.startswith('PMCID:') and record.get('pmcid', '').upper() != pmc:
        raise PaperError('Europe PMC returned a mismatched PMCID')
    if query.startswith('EXT_ID:') and (str(record.get('id')) != pmid or record.get('source') != 'MED'):
        raise PaperError('Europe PMC returned a mismatched PMID')
    if query.startswith('DOI:') and doi_value(record.get('doi') or '').lower() != doi.lower():
        raise PaperError('Europe PMC returned a mismatched DOI')
    return client._result('lookup', identifier, records)


def validate_xml(data, pmcid):
    if b'<!DOCTYPE' in data[:4096].upper() or b'<!ENTITY' in data[:65536].upper():
        raise PaperError('Article XML contains a DTD or entity declaration; nothing saved')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise PaperError('Europe PMC did not return valid article XML; nothing saved') from None
    local = lambda node: node.tag.split('}')[-1]
    if local(root) != 'article':
        raise PaperError('Europe PMC response is not article XML; nothing saved')
    ids = []
    front = next((child for child in root if local(child) == 'front'), None)
    for node in (front.iter() if front is not None else ()):
        if local(node) == 'article-id' and node.get('pub-id-type') in ('pmc', 'pmcid'):
            value = ''.join(node.itertext()).strip().upper()
            ids.append(value if value.startswith('PMC') else 'PMC'+value)
    if pmcid not in ids:
        raise PaperError('Article XML does not identify the requested PMCID; nothing saved')
    paragraphs = sum(1 for body in root.iter() if local(body) == 'body'
                     for node in body.iter() if local(node) == 'p')
    return {'format': 'JATS XML', 'body_paragraphs': paragraphs}


def validate_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(i.file_size for i in infos) > 250*1024*1024:
                raise PaperError('Supplement archive exceeds member count or expanded-size limit; nothing saved')
            for item in infos:
                name = item.filename.replace('\\', '/')
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
                    raise PaperError('Unsafe supplement member path; nothing saved')
            if archive.testzip():
                raise PaperError('Supplement ZIP failed its CRC check; nothing saved')
            return {'format': 'ZIP', 'members': [{'name': i.filename, 'bytes': i.file_size} for i in infos]}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, zlib.error) as exc:
        if isinstance(exc, PaperError):
            raise
        raise PaperError('Europe PMC did not return a readable supplement ZIP; nothing saved') from None


def download(client, identifier, kind, destination):
    if kind not in ('fulltext', 'supplements'):
        raise PaperError('Download kind must be fulltext or supplements')
    result = lookup(client, identifier)
    pmcid = result['papers'][0].get('pmcid') or ''
    if not re.fullmatch(r'PMC\d+', pmcid):
        raise PaperError('Record has no PMCID; no download attempted')
    path = Path(destination) / (pmcid+'.xml' if kind == 'fulltext' else pmcid+'_supplements.zip')
    if path.exists():
        raise PaperError('Download already exists; choose another scratch output folder')
    endpoint = '/'+pmcid+('/fullTextXML' if kind == 'fulltext' else '/supplementaryFiles')
    audit = {'endpoint': client.base+endpoint, 'parameters': {}, 'at_utc': datetime.now(timezone.utc).isoformat()}
    client.requests.append(audit)
    try:
        data = client.request_bytes(endpoint, {})
        digest = hashlib.sha256(data).hexdigest()
        audit['response'] = {'bytes': len(data), 'sha256': digest}
        info = validate_xml(data, pmcid) if kind == 'fulltext' else validate_zip(data)
        save_exclusive(path, data)
    except (PaperError, OSError) as exc:
        message = str(exc) if isinstance(exc, PaperError) else 'Could not save download; check output permissions'
        audit['error'] = message
        raise PaperError(message) from None
    result['operation'] = kind
    result['requests'] = client.requests
    result['download'] = {**info, 'path': str(path.resolve()), 'pmcid': pmcid,
                          'bytes': len(data), 'sha256': digest, 'verified_against_pdf': False}
    return client.snapshot(result)
