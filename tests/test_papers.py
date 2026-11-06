import io
import json
from urllib.error import HTTPError

import pytest

from literature_kit.papers import Client, PaperError, load_key, normalize


def test_key_env_overrides_config(tmp_path, monkeypatch):
    config = tmp_path / 'keys.toml'
    config.write_text('[papers.openalex]\napi_key="file-key"\n', encoding='utf-8')
    monkeypatch.setenv('LITERATURE_KIT_CONFIG', str(config))
    monkeypatch.setenv('OPENALEX_API_KEY', 'env-key')
    assert load_key('openalex') == 'env-key'
    monkeypatch.delenv('OPENALEX_API_KEY')
    assert load_key('openalex') == 'file-key'


def test_openalex_abstract_and_missing_fields():
    p = normalize('openalex', {'id': 'W1', 'abstract_inverted_index': {'cell': [1], 'A': [0]}})
    assert p['abstract'] == 'A cell'
    assert p['doi'] is None


def test_search_paginates_and_keeps_provenance():
    client = Client('openalex', 'secret', interval=0)
    calls = []
    def request(path, params):
        calls.append(dict(params))
        return {'results': [{'id': str(len(calls)), 'title': 'A'}],
                'meta': {'next_cursor': 'next' if len(calls) == 1 else None}}
    client.request = request
    result = client.search('cell biology', limit=2)
    assert len(result['papers']) == 2
    assert calls[1]['cursor'] == 'next'
    assert result['query'] == 'cell biology'
    assert len(result['requests']) == 2
    assert 'secret' not in json.dumps(result)


def test_retry_does_not_leak_key():
    client = Client('core', 'secret', interval=0, retries=1)
    calls = []
    def opener(req, timeout):
        calls.append(req)
        raise HTTPError(req.full_url + '&key=secret', 401, 'secret', {}, io.BytesIO(b'secret'))
    client.opener = opener
    with pytest.raises(PaperError) as exc:
        client.request('/works/1', {})
    assert 'secret' not in str(exc.value)
    assert len(calls) == 1


def test_retry_429_honours_delay(monkeypatch):
    client = Client('semantic-scholar', 'secret', interval=0, retries=1)
    delays = []
    monkeypatch.setattr('literature_kit.papers.time.sleep', delays.append)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return b'{"data": []}'
    def opener(req, timeout):
        calls.append(req)
        if len(calls) == 1:
            raise HTTPError(req.full_url, 429, 'busy', {'Retry-After': '2'}, io.BytesIO())
        return Response()
    client.opener = opener
    assert client.request('/paper/search', {}) == {'data': []}
    assert delays == [2]


def test_core_doi_lookup_uses_exact_field_and_normalizes():
    client = Client('core', 'secret', interval=0)
    calls = []
    def request(path, params):
        calls.append((path, params))
        return {'results': [{'id': 3, 'doi': '10.1/test', 'authors': [{'name': 'Smith'}]}]}
    client.request = request
    result = client.lookup('https://doi.org/10.1/test')
    assert calls[0][1]['q'] == 'doi:"10.1/test"'
    assert result['papers'][0]['authors'] == ['Smith']


def test_recommendation_rejects_unsupported_provider():
    with pytest.raises(PaperError):
        Client('core', 'key', interval=0).recommend('10.1/example', 5)


@pytest.mark.parametrize('provider', ['core', 'semantic-scholar'])
def test_offset_pagination(provider):
    client = Client(provider, 'secret', interval=0)
    offsets = []
    def request(path, params):
        offsets.append(params['offset'])
        if provider == 'core':
            return {'results': [{'id': len(offsets)}], 'totalHits': 2}
        return {'data': [{'paperId': str(len(offsets))}], 'next': 1 if len(offsets) == 1 else None}
    client.request = request
    assert len(client.search('protein', 2)['papers']) == 2
    assert offsets == [0, 1]


def test_cli_saves_failed_search_without_leaking_key(tmp_path, monkeypatch, capsys):
    import literature_kit.papers as papers
    from literature_kit.papers import main
    from literature_kit.config import Paths
    monkeypatch.setenv('CORE_API_KEY', 'secret-value')
    monkeypatch.setattr(papers, 'load_paths', lambda: Paths(tmp_path))
    def request(self, path, params):
        raise PaperError('core: HTTP 401; check key, quota or query')
    monkeypatch.setattr(Client, 'request', request)
    assert main(['search', '--provider', 'core', '--query', 'protein']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['query'] == 'protein'
    assert result['error']
    saved = list((tmp_path / 'papers-api').glob('*.json'))
    assert len(saved) == 1
    assert 'secret-value' not in saved[0].read_text(encoding='utf-8')


def test_recommendation_endpoint_and_doi_encoding():
    client = Client('semantic-scholar', 'key', interval=0)
    calls = []
    def request(path, params):
        calls.append(path)
        return {'recommendedPapers': [{'paperId': 'abc', 'title': 'Related'}]}
    client.request = request
    assert client.recommend('10.1/a', 1)['papers'][0]['title'] == 'Related'
    assert calls == ['/recommendations/v1/papers/forpaper/DOI:10.1/a']


def test_auth_in_header_not_url_and_response_redacted():
    client = Client('openalex', 'private-key', interval=0)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return b'{"id":"W1","note":"private-key"}'
    def opener(req, timeout):
        assert 'private-key' not in req.full_url
        assert req.get_header('Authorization') == 'Bearer private-key'
        return Response()
    client.opener = opener
    assert 'private-key' not in json.dumps(client.lookup('W1'))


def test_long_retry_after_stops_without_sleep(monkeypatch):
    client = Client('core', 'key', interval=0)
    def opener(req, timeout):
        raise HTTPError(req.full_url, 429, 'busy', {'Retry-After': '3600'}, io.BytesIO())
    client.opener = opener
    with pytest.raises(PaperError, match='3600'):
        client.request('/works/1', {})


def test_core_uses_canonical_trailing_slash():
    client = Client('core', 'key', interval=0)
    calls = []
    def request(path, params):
        calls.append(path)
        return {'results': [], 'totalHits': 0}
    client.request = request
    client.search('protein', 1)
    assert calls == ['/search/works/']


def test_semantic_doi_route_preserves_slash():
    client = Client('semantic-scholar', 'key', interval=0)
    calls = []
    def request(path, params):
        calls.append(path)
        return {'paperId': 'abc'}
    client.request = request
    client.lookup('10.1038/nature14539')
    assert calls == ['/graph/v1/paper/DOI:10.1038/nature14539']
