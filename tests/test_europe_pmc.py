import io
import json
import zipfile
from pathlib import Path

import pytest

from literature_kit.papers import Client, PaperError, normalize, load_key


def record():
    return {'id': '123', 'source': 'MED', 'pmcid': 'PMC123', 'doi': '10.1234/test',
            'title': 'Cells', 'authorList': {'author': [{'fullName': 'A Smith'}]},
            'abstractText': '<p>Example.</p>', 'pubYear': '2025'}


def client():
    return Client('europe-pmc', interval=0)


def test_keyless_normalization():
    assert load_key('europe-pmc') == ''
    p = normalize('europe-pmc', record())
    assert p['pmcid'] == 'PMC123'
    assert p['authors'] == ['A Smith']
    assert p['year'] == 2025


def test_cursor_paging():
    c = client()
    calls = []
    def request(path, params):
        calls.append(dict(params))
        return {'hitCount': 2, 'nextCursorMark': 'next' if len(calls) == 1 else 'end',
                'resultList': {'result': [record()]}}
    c.request = request
    result = c.search('TITLE:Cells', 2)
    assert len(result['papers']) == 2
    assert calls[1]['cursorMark'] == 'next'
    assert result['requests'][0]['parameters']['resultType'] == 'core'
    assert result['papers'][0]['title'] == 'Cells'


@pytest.mark.parametrize('identifier,query', [
    ('PMC123', 'PMCID:PMC123'), ('PMCID:PMC123', 'PMCID:PMC123'),
    ('PMID:123', 'EXT_ID:123 AND SRC:MED'), ('123', 'EXT_ID:123 AND SRC:MED'),
    ('https://doi.org/10.1234/test', 'DOI:"10.1234/test"')])
def test_lookup_formats(identifier, query):
    c = client()
    def request(path, params):
        assert params['query'] == query
        return {'hitCount': 1, 'resultList': {'result': [record()]}}
    c.request = request
    assert c.lookup(identifier)['papers'][0]['doi'] == '10.1234/test'


@pytest.mark.parametrize('count', [0, 2])
def test_ambiguous_or_missing_lookup(count):
    c = client()
    c.request = lambda path, params: {'hitCount': count, 'resultList': {'result': [record()] * count}}
    with pytest.raises(PaperError):
        c.lookup('123')


def download_client(data):
    c = client()
    c.request = lambda path, params: {'hitCount': 1, 'resultList': {'result': [record()]}}
    c.request_bytes = lambda path, params: data
    return c


def xml(pmc='123'):
    return f'<article><front><article-meta><article-id pub-id-type="pmc">{pmc}</article-id></article-meta></front><body><p>Cell</p></body></article>'.encode()


def test_fulltext_identity_and_no_overwrite(tmp_path):
    c = download_client(xml())
    result = c.download('PMC123', 'fulltext', tmp_path)
    assert result['download']['format'] == 'JATS XML'
    assert (tmp_path / 'PMC123.xml').read_bytes() == xml()
    assert result['download']['body_paragraphs'] == 1
    with pytest.raises(PaperError, match='exists'):
        c.download('PMC123', 'fulltext', tmp_path)


@pytest.mark.parametrize('data', [b'<html/>', xml('999'), b'not xml'])
def test_reject_wrong_article(tmp_path, data):
    with pytest.raises(PaperError):
        download_client(data).download('123', 'fulltext', tmp_path)
    assert not list(tmp_path.iterdir())


def archive(name='mmc1.txt'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(name, 'data')
    return buf.getvalue()


def test_supplements_manifest_no_extraction(tmp_path):
    result = download_client(archive()).download('123', 'supplements', tmp_path)
    assert result['download']['members'] == [{'name': 'mmc1.txt', 'bytes': 4}]
    assert not (tmp_path / 'mmc1.txt').exists()
    assert (tmp_path / 'PMC123_supplements.zip').exists()


def test_reject_unsafe_archive(tmp_path):
    with pytest.raises(PaperError):
        download_client(archive('../bad')).download('123', 'supplements', tmp_path)
    assert not list(tmp_path.iterdir())


def test_keyless_request_has_no_auth_header():
    c = client()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return b'{"hitCount":0}'
    def opener(req, timeout):
        assert not req.has_header('Authorization')
        assert not req.has_header('X-api-key')
        return Response()
    c.opener = opener
    assert c.request('/search', {})['hitCount'] == 0


def test_cli_status_and_download_parser(capsys):
    from literature_kit.papers import main
    assert main(['status']) == 0
    status = json.loads(capsys.readouterr().out)['providers']['europe-pmc']
    assert status['configured'] and status['requires_key'] is False


def test_download_cli_uses_scratch_out(tmp_path, monkeypatch, capsys):
    import literature_kit.papers as papers
    from literature_kit.config import Paths
    from literature_kit.papers import main
    monkeypatch.setattr(papers, 'load_paths', lambda: Paths(tmp_path))
    def download(self, identifier, kind, folder):
        assert folder == tmp_path / 'papers-api/downloads/check'
        return {'papers': [], 'download': {'path': str(folder / 'PMC123.xml')}}
    monkeypatch.setattr(Client, 'download', download)
    assert main(['fulltext','--provider','europe-pmc','--id','PMC123','--out','check']) == 0
    assert json.loads(capsys.readouterr().out)['download']


def test_bounded_binary_response(monkeypatch):
    import literature_kit.papers as papers
    monkeypatch.setattr(papers, 'MAX_RESPONSE_BYTES', 8)
    c = client()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == 9
            return b'123456789'
    c.opener = lambda req, timeout: Response()
    with pytest.raises(PaperError, match='exceeds'):
        c.request_bytes('/PMC123/fullTextXML', {})


def test_cli_rejects_download_outside_scratch(tmp_path, monkeypatch, capsys):
    import literature_kit.papers as papers
    from literature_kit.config import Paths
    from literature_kit.papers import main
    monkeypatch.setattr(papers, 'load_paths', lambda: Paths(tmp_path / 'scratch'))
    def download(*args):
        pytest.fail('Must not download outside scratch')
    monkeypatch.setattr(Client, 'download', download)
    assert main(['fulltext','--provider','europe-pmc','--id','PMC123','--out', str(tmp_path / 'outside')]) == 1
    assert 'inside' in json.loads(capsys.readouterr().out)['error']


def test_validate_xml_rejects_entity_declarations_and_nested_ids():
    from literature_kit.europe_pmc import validate_xml
    bomb = b'<?xml version="1.0"?><!DOCTYPE article [<!ENTITY a "x">]><article><front/></article>'
    with pytest.raises(PaperError, match='DTD'):
        validate_xml(bomb, 'PMC1')
    nested = (b'<article><front><article-meta><article-id pub-id-type="pmc">1</article-id></article-meta></front>'
              b'<body><sub-article><front><article-meta><article-id pub-id-type="pmc">2</article-id></article-meta></front></sub-article></body></article>')
    assert validate_xml(nested, 'PMC1')['format'] == 'JATS XML'
    with pytest.raises(PaperError, match='requested PMCID'):
        validate_xml(nested, 'PMC2')
