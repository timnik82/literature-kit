"""Read-only literature APIs; reusable Python clients and the `papers` CLI group.

No credentials in URLs, error messages or saved results. No remote catalogue writes.
"""
from __future__ import annotations

import json
import hashlib
import tempfile
import threading
from http.client import HTTPException
import os
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from literature_kit.config import ConfigError, _read_config, find_config_file, load_paths

PROVIDERS = {
    'openalex': ('https://api.openalex.org', 'OPENALEX_API_KEY', 0.11),
    'semantic-scholar': ('https://api.semanticscholar.org', 'SEMANTIC_SCHOLAR_API_KEY', 1.1),
    'core': ('https://api.core.ac.uk/v3', 'CORE_API_KEY', 2.1),
    'europe-pmc': ('https://www.ebi.ac.uk/europepmc/webservices/rest', None, 0.4),
}
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_AUDIT_BYTES = 64 * 1024 * 1024
_PACING_REGISTRY_LOCK = threading.Lock()
_PACING_GATES = {}


class _PacingGate:
    def __init__(self):
        self.lock = threading.Lock()
        self.last = None


def save_exclusive(path: Path, data: bytes) -> None:
    """Publish a fully written file atomically without replacing an existing file."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.part', dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Same-directory hard link is atomic and fails if the final name exists.
        os.link(temporary, path)
    except FileExistsError:
        raise PaperError('File already exists; nothing overwritten') from None
    except OSError:
        raise PaperError('Could not save file; check disk space and output permissions') from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # A cleanup failure must never publish a partial final file.

FIELDS = 'title,abstract,year,authors,externalIds,url,openAccessPdf,citationCount'


class PaperError(RuntimeError):
    pass


def load_key(provider: str) -> str:
    if provider not in PROVIDERS:
        raise PaperError('Unknown paper provider')
    if provider == 'europe-pmc':
        return ''
    papers_table = _read_config(None)[0].get('papers', {})
    if not isinstance(papers_table, dict):
        raise ConfigError('[papers] in the config file must be a table')
    table = papers_table.get(provider, {})
    if not isinstance(table, dict):
        raise ConfigError(f'[papers.{provider}] in the config file must be a table')
    file_key = table.get('api_key', '')
    if not isinstance(file_key, str):
        raise ConfigError(f'api_key in [papers.{provider}] in the config file must be a string')
    key = os.environ.get(PROVIDERS[provider][1]) or file_key
    return str(key).strip()


def doi_value(value: str) -> str:
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:)', '', value.strip(), flags=re.I)


def normalize(provider: str, record: dict, fulltext: bool = False) -> dict:
    if provider == 'europe-pmc':
        from literature_kit.europe_pmc import normalize as epmc_normalize
        return {'provider': provider, **epmc_normalize(record)}
    if provider == 'openalex':
        index = record.get('abstract_inverted_index') or {}
        words = sorted((pos, word) for word, positions in index.items() for pos in positions)
        abstract = ' '.join(word for _, word in words) or None
        authors = [(a.get('author') or {}).get('display_name') for a in (record.get('authorships') or [])]
        location = record.get('best_oa_location') or record.get('primary_location') or {}
        doi = record.get('doi')
        result = dict(id=record.get('id'), title=record.get('title'), abstract=abstract,
                      year=record.get('publication_year'), authors=authors, doi=doi_value(doi) if doi else None,
                      url=record.get('id'), pdf_url=location.get('pdf_url'),
                      citation_count=record.get('cited_by_count'), content_urls=record.get('content_urls'))
    elif provider == 'semantic-scholar':
        result = dict(id=record.get('paperId'), title=record.get('title'), abstract=record.get('abstract'),
                      year=record.get('year'), authors=[a.get('name') for a in (record.get('authors') or [])],
                      doi=(record.get('externalIds') or {}).get('DOI'), url=record.get('url'),
                      pdf_url=(record.get('openAccessPdf') or {}).get('url'),
                      citation_count=record.get('citationCount'))
    else:
        doi = record.get('doi')
        result = dict(id=record.get('id'), title=record.get('title'), abstract=record.get('abstract'),
                      year=record.get('yearPublished'), authors=[a.get('name') if isinstance(a, dict) else a
                                                               for a in (record.get('authors') or [])],
                      doi=doi_value(doi) if doi else None,
                      url=f"https://core.ac.uk/works/{record.get('id')}", pdf_url=record.get('downloadUrl'),
                      citation_count=None)
        if fulltext:
            result['full_text'] = record.get('fullText') or None
    return {'provider': provider, **result}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward API credentials to a redirected host.
        return None


class Client:
    def __init__(self, provider: str, key: str | None = None, *, interval=None, retries=3):
        if provider not in PROVIDERS:
            raise PaperError('Unknown paper provider')
        self.provider = provider
        self.base, self.env, default_interval = PROVIDERS[provider]
        self.key = '' if provider == 'europe-pmc' else (load_key(provider) if key is None else key)
        if self.env and not self.key:
            raise PaperError(f'Set {self.env} or [papers.{provider}] api_key in literature-kit.local.toml')
        self.interval = default_interval if interval is None else interval
        self.retries = retries
        identity = (provider, hashlib.sha256(self.key.encode('utf-8')).digest())
        with _PACING_REGISTRY_LOCK:
            self._gate = _PACING_GATES.setdefault(identity, _PacingGate())
        self.requests = []
        self._audit_bytes = 0
        self.opener = build_opener(_NoRedirect()).open

    def request(self, path: str, params: dict) -> dict:
        try:
            data = json.loads(self.request_bytes(path, params))
        except (ValueError, UnicodeError):
            raise PaperError(f'{self.provider}: invalid JSON response') from None
        if not isinstance(data, dict):
            raise PaperError(f'{self.provider}: unexpected JSON response')
        return data

    def request_bytes(self, path: str, params: dict) -> bytes:
        if not path.startswith('/') or path.startswith('//') or '?' in path:
            raise PaperError('Expected a relative API endpoint')
        headers = {'Accept': 'application/json', 'User-Agent': 'literature-kit/papers'}
        if self.env:
            headers['x-api-key' if self.provider == 'semantic-scholar' else 'Authorization'] = (
                self.key if self.provider == 'semantic-scholar' else f'Bearer {self.key}')
        else:
            headers['Accept'] = 'application/json, application/xml, application/zip'
        url = self.base + path + ('?' + urlencode(params) if params else '')
        for attempt in range(self.retries + 1):
            # Starts are serialized across clients/threads sharing a provider/key.
            with self._gate.lock:
                if self._gate.last is not None:
                    wait = self.interval - (time.monotonic() - self._gate.last)
                    if wait > 0:
                        time.sleep(wait)
                self._gate.last = time.monotonic()
            try:
                with self.opener(Request(url, headers=headers), timeout=30) as response:
                    data = response.read(MAX_RESPONSE_BYTES+1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise PaperError(f'{self.provider}: response exceeds 50 MiB; nothing saved')
                return data
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise PaperError(f'{self.provider}: HTTP {exc.code}; check key, quota or query') from None
                retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 2 ** attempt
                if delay > 60:
                    raise PaperError(f'{self.provider}: rate limited; retry after {int(delay)} seconds') from None
                time.sleep(max(0, delay))
            except (URLError, TimeoutError, OSError, HTTPException):
                if attempt == self.retries:
                    raise PaperError(f'{self.provider}: network request failed') from None
                time.sleep(2 ** attempt)
            except (ValueError, UnicodeError):
                raise PaperError(f'{self.provider}: invalid JSON response') from None
        raise PaperError('Request failed')

    def _fetch(self, path, params):
        if self.provider == 'core' and path.rstrip('/') == '/search/works':
            path = '/search/works/'
        audit = {'endpoint': self.base + path, 'parameters': dict(params),
                 'at_utc': datetime.now(timezone.utc).isoformat()}
        self.requests.append(audit)
        try:
            data = self.request(path, params)
        except PaperError as exc:
            audit['error'] = str(exc)
            raise
        size = len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        if self._audit_bytes + size > MAX_AUDIT_BYTES:
            audit['error'] = 'Client audit response budget exceeded; narrow the query or start a new client'
            audit['response_bytes'] = size
            raise PaperError(audit['error'])
        self._audit_bytes += size
        audit['response'] = data
        return data

    def _result(self, operation, query, records, fulltext=False):
        result = {'provider': self.provider, 'operation': operation, 'query': query,
                  'at_utc': datetime.now(timezone.utc).isoformat(),
                  'papers': [normalize(self.provider, r, fulltext) for r in records],
                  'requests': self.requests}
        # Defense against a provider echoing a credential in its response.
        return self.snapshot(result)

    def snapshot(self, result):
        """Detach nested audit data and redact provider-echoed credentials."""
        detached = json.loads(json.dumps(result, ensure_ascii=False))
        return _redact_secrets(detached, {self.key: '[REDACTED]'} if self.key else {})

    def search(self, query: str, limit: int = 20, *, filter_value: str | None = None):
        if not query.strip() or not 1 <= limit <= 1000:
            raise PaperError('Supply a query and a limit between 1 and 1000')
        if self.provider == 'europe-pmc':
            from literature_kit.europe_pmc import search
            return search(self, query, limit, filter_value)
        if filter_value and self.provider != 'openalex':
            raise PaperError('--filter is supported only for OpenAlex; use native query syntax for CORE')
        records, cursor, offset = [], '*', 0
        while len(records) < limit:
            size = min(100, limit - len(records))
            if self.provider == 'openalex':
                params = {'search': query, 'per_page': size, 'cursor': cursor}
                if filter_value:
                    params['filter'] = filter_value
                data = self._fetch('/works', params)
                batch = data.get('results', [])
                next_value = (data.get('meta') or {}).get('next_cursor')
            elif self.provider == 'semantic-scholar':
                data = self._fetch('/graph/v1/paper/search',
                                   {'query': query, 'limit': size, 'offset': offset, 'fields': FIELDS})
                batch = data.get('data', [])
                next_value = data.get('next')
            else:
                data = self._fetch('/search/works', {'q': query, 'limit': size, 'offset': offset})
                batch = data.get('results', [])
                next_value = offset + len(batch) if batch and offset + len(batch) < data.get('totalHits', 0) else None
            records.extend(batch[:limit - len(records)])
            if not batch or next_value is None or next_value == cursor or next_value == offset:
                break
            if self.provider == 'openalex':
                cursor = next_value
            else:
                if not isinstance(next_value, int) or next_value <= offset:
                    break
                offset = next_value
        return self._result('search', query, records)

    def lookup(self, identifier: str, *, fulltext: bool = False):
        if self.provider == 'europe-pmc':
            if fulltext:
                raise PaperError('Use papers fulltext for Europe PMC XML downloads')
            from literature_kit.europe_pmc import lookup
            return lookup(self, identifier)
        value = doi_value(identifier)
        if not value:
            raise PaperError('Supply a DOI or provider identifier')
        if fulltext and self.provider != 'core':
            raise PaperError('--fulltext currently supports CORE only')
        if self.provider == 'openalex':
            ident = 'https://doi.org/' + value if value.startswith('10.') else value.removeprefix('https://openalex.org/')
            records = [self._fetch('/works/' + quote(ident, safe=''), {})]
        elif self.provider == 'semantic-scholar':
            ident = 'DOI:' + value if value.startswith('10.') else value
            records = [self._fetch('/graph/v1/paper/' + quote(ident, safe=':/'), {'fields': FIELDS})]
        elif value.startswith('10.'):
            if any(c in value for c in ('"', '\\', '\n', '\r')):
                raise PaperError('Unsupported character in DOI')
            candidates = self._fetch('/search/works', {'q': f'doi:"{value}"', 'limit': 100})
            records = [r for r in candidates.get('results', []) if doi_value(r.get('doi') or '').lower() == value.lower()]
            if fulltext:
                detailed = []
                for record in records:
                    if record.get('id') is None:
                        raise PaperError('core: search result has no work id; cannot fetch full text')
                    detailed.append(self._fetch('/works/' + quote(str(record['id']), safe=''), {}))
                records = detailed
        else:
            if not value.isdigit():
                raise PaperError('CORE lookup accepts a DOI or numeric CORE work ID')
            records = [self._fetch('/works/' + value, {})]
        if not records:
            raise PaperError(f'{self.provider}: no matching paper found')
        return self._result('lookup', identifier, records, fulltext)

    def download(self, identifier, kind, destination):
        if self.provider != 'europe-pmc':
            raise PaperError('File downloads currently require --provider europe-pmc')
        from literature_kit.europe_pmc import download
        return download(self, identifier, kind, destination)

    def recommend(self, identifier: str, limit: int = 20):
        if self.provider != 'semantic-scholar':
            raise PaperError('Recommendations require --provider semantic-scholar')
        if not 1 <= limit <= 500:
            raise PaperError('Recommendation limit must be between 1 and 500')
        value = doi_value(identifier)
        ident = 'DOI:' + value if value.startswith('10.') else value
        data = self._fetch('/recommendations/v1/papers/forpaper/' + quote(ident, safe=':/'),
                           {'limit': limit, 'fields': FIELDS})
        return self._result('recommend', identifier, data.get('recommendedPapers', []))


def _redact_text(text, key, marker):
    if text == key:
        return marker
    for variant in {key, json.dumps(key, ensure_ascii=False)[1:-1], json.dumps(key)[1:-1]}:
        if not variant:
            continue
        if text == variant:
            return marker
        text = text.replace(f'Bearer {variant}', marker)
        text = re.sub(r'(?i)((?:api[-_]?key|key|authorization)\s*[:=]\s*["\']?)' + re.escape(variant),
                      r'\g<1>' + marker, text)
        # A long random key appearing verbatim cannot be legitimate prose;
        # short keys are only redacted exactly or in delimited contexts so
        # ordinary words containing them survive.
        if len(variant) >= 16:
            text = text.replace(variant, marker)
    return text


def _redact_secrets(obj, secrets):
    """Copy ``obj`` replacing exact/delimited occurrences of each key."""
    if isinstance(obj, dict):
        return {_redact_secrets(k, secrets): _redact_secrets(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_secrets(v, secrets) for v in obj]
    if isinstance(obj, tuple):
        return [_redact_secrets(v, secrets) for v in obj]
    if isinstance(obj, str):
        for key, marker in secrets.items():
            if key:
                obj = _redact_text(obj, key, marker)
        return obj
    return obj


def _redacted_json(result):
    """Serialize a CLI result with any configured API key value replaced, so a key can never reach stdout or an audit file."""
    secrets = {}
    for provider in PROVIDERS:
        try:
            key = load_key(provider)
        except Exception:
            continue
        if key:
            secrets[key] = '[redacted]'
    return json.dumps(_redact_secrets(result, secrets), ensure_ascii=False, indent=2)


def run(args):
    if args.paper_action == 'status':
        config = find_config_file()
        print(json.dumps({'config_file': str(config) if config else None,
                          'scratch_dir': str(load_paths().scratch_dir) if load_paths().scratch_dir else None,
                          'providers': {p: {'configured': not v[1] or bool(load_key(p)), 'requires_key': bool(v[1]), 'environment_variable': v[1]}
                                        for p, v in PROVIDERS.items()}}, indent=2))
        return 0
    client = None
    path = None
    query = getattr(args, 'query', None) or getattr(args, 'id', None)
    try:
        # Resolve writable destination before making calls that consume quota.
        destination = load_paths().require_scratch() / 'papers-api'
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex + '.json')
        client = Client(args.provider)
        if args.paper_action == 'search':
            result = client.search(args.query, args.limit, filter_value=args.filter)
        elif args.paper_action == 'lookup':
            result = client.lookup(args.id, fulltext=args.fulltext)
        elif args.paper_action in ('fulltext', 'supplements'):
            folder = destination / 'downloads'
            if args.out:
                folder = Path(args.out).expanduser()
                if not folder.is_absolute():
                    folder = destination / 'downloads' / folder
            if not folder.resolve().is_relative_to(load_paths().require_scratch().resolve()):
                raise PaperError('--out must remain inside the configured scratch folder')
            result = client.download(args.id, args.paper_action, folder)
        else:
            result = client.recommend(args.id, args.limit)
    except (RuntimeError, ValueError, OSError) as exc:
        result = (client._result(args.paper_action, query, []) if client is not None else
                  {'provider': args.provider, 'operation': args.paper_action, 'query': query,
                   'at_utc': datetime.now(timezone.utc).isoformat(), 'papers': [], 'requests': []})
        result['error'] = str(exc) if isinstance(exc, (PaperError, ConfigError)) else 'Command setup or output failed; check paths and permissions'
    result['search_id'] = args.search_id
    result['saved_to'] = str(path) if path else None
    result['audit_saved'] = path is not None
    if path is not None:
        try:
            save_exclusive(path, _redacted_json(result).encode('utf-8'))
        except PaperError:
            result['audit_saved'] = False
            result['saved_to'] = None
            result['error'] = result.get('error', 'Command completed') + '; could not save audit file'
    print(_redacted_json(result))
    return 1 if 'error' in result else 0


def add_parser(sub):
    parser = sub.add_parser('papers', help='Literature APIs: OpenAlex, Semantic Scholar, CORE, Europe PMC (JSON + scratch audit)')
    _add_actions(parser)


def _add_actions(parser):
    actions = parser.add_subparsers(dest='paper_action', required=True)
    actions.add_parser('status', help='show key presence and config path, without API calls').set_defaults(func=run)
    for action in ('search', 'lookup', 'recommend', 'fulltext', 'supplements'):
        p = actions.add_parser(action)
        p.add_argument('--provider', required=True, choices=('europe-pmc',) if action in ('fulltext', 'supplements') else PROVIDERS)
        p.add_argument('--search-id', help='project search/catalogue ID, e.g. S12; caller must check duplicates and log the search')
        if action == 'search':
            p.add_argument('--query', required=True)
            p.add_argument('--filter', help='native OpenAlex filter expression')
        else:
            p.add_argument('--id', required=True, help='DOI or provider paper/work ID')
        if action == 'lookup':
            p.add_argument('--fulltext', action='store_true', help='include CORE fullText when available')
        elif action in ('fulltext', 'supplements'):
            p.add_argument('--out', help='scratch subfolder or absolute folder inside scratch (never overwrites)')
        else:
            p.add_argument('--limit', type=int, default=20)
        p.set_defaults(func=run)


def main(argv=None):
    """Project-independent literature CLI (`literature-kit`)."""
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(
        prog='literature-kit',
        description='Scholarly discovery, identifier lookup and available full text across projects.',
    )
    _add_actions(parser)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
