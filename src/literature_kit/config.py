"""Machine-specific settings: where audits are written and where API keys are read.

Scratch folder, resolved in this order:
1. ``LITERATURE_KIT_SCRATCH_DIR`` (legacy fallbacks: ``LITKIT_SCRATCH_DIR``, ``LACAIXA_SCRATCH_DIR``).
2. ``scratch_dir`` in the config file.

Config file (optional; holds provider keys and may hold ``scratch_dir``):
``LITERATURE_KIT_CONFIG`` (fallbacks ``LITKIT_CONFIG``, ``LACAIXA_CONFIG``), else
``literature-kit.local.toml`` (fallbacks ``litkit.local.toml``, ``lacaixa.local.toml``) in the
current directory or any parent, else in the source checkout.

Relative paths in the file resolve against the file's folder; relative environment values
against the current directory. Never set a global scratch folder shared across projects.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAMES = ("literature-kit.local.toml", "litkit.local.toml", "lacaixa.local.toml")
_SOURCE_CHECKOUT = Path(__file__).resolve().parents[2]


def _env(*names: str) -> str | None:
    for name in names:
        if value := os.environ.get(name):
            return value
    return None


@dataclass(frozen=True)
class Paths:
    scratch_dir: Path | None

    def require_scratch(self) -> Path:
        if self.scratch_dir is None:
            raise RuntimeError(
                "scratch_dir is not set: define LITERATURE_KIT_SCRATCH_DIR or scratch_dir in a config file"
            )
        return self.scratch_dir


def find_config_file() -> Path | None:
    if explicit := _env("LITERATURE_KIT_CONFIG", "LITKIT_CONFIG", "LACAIXA_CONFIG"):
        return Path(explicit).expanduser().resolve()
    cwd = Path.cwd().resolve()
    seen: set[Path] = set()
    for folder in (cwd, *cwd.parents, _SOURCE_CHECKOUT):
        if folder in seen:
            continue
        seen.add(folder)
        for name in CONFIG_NAMES:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def _as_path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _read_config(config_file: Path | None) -> tuple[dict, Path]:
    if config_file is None:
        config_file = find_config_file()
    if config_file is not None and config_file.is_file():
        with config_file.open("rb") as fh:
            return tomllib.load(fh), config_file.resolve().parent
    return {}, Path.cwd()


def load_paths(config_file: Path | None = None) -> Paths:
    values, base = _read_config(config_file)
    if env_value := _env("LITERATURE_KIT_SCRATCH_DIR", "LITKIT_SCRATCH_DIR", "LACAIXA_SCRATCH_DIR"):
        return Paths(scratch_dir=_as_path(env_value, Path.cwd()))
    return Paths(scratch_dir=_as_path(values.get("scratch_dir"), base))
