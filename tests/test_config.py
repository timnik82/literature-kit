from literature_kit.config import load_paths


def _clear(monkeypatch):
    for name in ("LITERATURE_KIT_SCRATCH_DIR", "LITKIT_SCRATCH_DIR", "LACAIXA_SCRATCH_DIR",
                 "LITERATURE_KIT_CONFIG", "LITKIT_CONFIG", "LACAIXA_CONFIG"):
        monkeypatch.delenv(name, raising=False)


def test_env_wins_and_legacy_names_still_work(tmp_path, monkeypatch):
    _clear(monkeypatch)
    cfg = tmp_path / "c.toml"
    cfg.write_text("scratch_dir = 'from-file'\n")
    monkeypatch.setenv("LACAIXA_SCRATCH_DIR", str(tmp_path / "legacy"))
    assert load_paths(cfg).scratch_dir == tmp_path / "legacy"
    monkeypatch.setenv("LITKIT_SCRATCH_DIR", str(tmp_path / "mid"))
    assert load_paths(cfg).scratch_dir == tmp_path / "mid"
    monkeypatch.setenv("LITERATURE_KIT_SCRATCH_DIR", str(tmp_path / "new"))
    assert load_paths(cfg).scratch_dir == tmp_path / "new"


def test_unset_scratch_is_none(tmp_path, monkeypatch):
    _clear(monkeypatch)
    assert load_paths(tmp_path / "absent.toml").scratch_dir is None


def test_relative_file_path_resolves_against_config_folder(tmp_path, monkeypatch):
    _clear(monkeypatch)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    cfg = cfg_dir / "literature-kit.local.toml"
    cfg.write_text('scratch_dir = "scratch"\n')
    monkeypatch.chdir(tmp_path)
    assert load_paths(cfg).scratch_dir == cfg_dir / "scratch"


def test_config_found_in_parent_folder_by_any_name(tmp_path, monkeypatch):
    _clear(monkeypatch)
    scratch = tmp_path / "abs-scratch"
    (tmp_path / "lacaixa.local.toml").write_text(f"scratch_dir = '{scratch}'\n")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert load_paths().scratch_dir == scratch


def test_explicit_missing_config_and_bad_scratch_type_are_reported(tmp_path, monkeypatch):
    import pytest
    from literature_kit.config import ConfigError
    _clear(monkeypatch)
    monkeypatch.setenv("LITERATURE_KIT_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(ConfigError, match="not found"):
        load_paths()
    monkeypatch.delenv("LITERATURE_KIT_CONFIG")
    bad = tmp_path / "bad.toml"
    bad.write_text("scratch_dir = 5\n")
    with pytest.raises(ConfigError, match="string"):
        load_paths(bad)


def test_invalid_toml_is_a_config_error(tmp_path, monkeypatch):
    import pytest
    from literature_kit.config import ConfigError
    _clear(monkeypatch)
    bad = tmp_path / "bad.toml"
    bad.write_text("scratch_dir = \n")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_paths(bad)


def test_non_utf8_config_is_a_config_error(tmp_path, monkeypatch):
    import pytest
    from literature_kit.config import ConfigError
    _clear(monkeypatch)
    bad = tmp_path / "bad.toml"
    bad.write_bytes(bytes([0xff]) + b" = 1")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_paths(bad)
