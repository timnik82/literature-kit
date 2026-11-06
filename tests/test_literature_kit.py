import json

import pytest

from literature_kit.papers import main


def test_status_without_network(capsys):
    assert main(['status']) == 0
    current = json.loads(capsys.readouterr().out)
    assert set(current['providers']) == {'openalex', 'semantic-scholar', 'core', 'europe-pmc'}


def test_python_m_status_and_import_is_side_effect_free():
    import subprocess
    import sys
    imported = subprocess.run([sys.executable, '-c', 'import literature_kit.__main__'],
                              capture_output=True, text=True)
    assert imported.returncode == 0
    assert imported.stdout == ''
    ran = subprocess.run([sys.executable, '-m', 'literature_kit', 'status'],
                         capture_output=True, text=True)
    assert ran.returncode == 0
    assert 'europe-pmc' in ran.stdout


def test_help_exposes_direct_operations(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert 'usage: literature-kit ' in help_text
    for operation in ('status', 'search', 'lookup', 'recommend', 'fulltext', 'supplements'):
        assert operation in help_text


def test_failed_search_saves_audit_in_selected_project_scratch(tmp_path, monkeypatch, capsys):
    scratch = tmp_path / 'scratch'
    config = tmp_path / 'empty.toml'
    config.write_text('', encoding='utf-8')
    monkeypatch.setenv('LITERATURE_KIT_CONFIG', str(config))
    monkeypatch.setenv('LITERATURE_KIT_SCRATCH_DIR', str(scratch))
    monkeypatch.delenv('CORE_API_KEY', raising=False)
    assert main(['search', '--provider', 'core', '--query', 'protein', '--limit', '1',
                 '--search-id', 'TEST']) == 1
    result = json.loads(capsys.readouterr().out)
    assert 'CORE_API_KEY' in result['error']
    assert result['audit_saved'] is True
    from pathlib import Path
    saved = Path(result['saved_to'])
    assert saved.parent == scratch / 'papers-api'
    assert json.loads(saved.read_text(encoding='utf-8'))['search_id'] == 'TEST'
