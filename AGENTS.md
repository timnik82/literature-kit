# AGENTS.md — literature-kit

Project-independent literature tools. Keep this repository free of any project's paths, document names, search
logs, credentials or catalogue rules; those belong to the project that uses the tool.

- Code: `src/literature_kit/` (`papers.py` commands and clients, `europe_pmc.py`, `config.py`). Python 3.11+, no runtime dependencies.
- Install on this machine: `uv tool install --editable <checkout>` puts `literature-kit` on PATH via `~/.local/bin`; re-run after pulling changes only if entry points change. Provider keys come from user env vars (`OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `CORE_API_KEY`); Europe PMC needs none. Per-project routing: drop a `literature-kit.local.toml` with `scratch_dir` in the project's root (auto-discovered from cwd); check with `literature-kit status`.
- Tests are offline (`uv run pytest`). Do not commit keys, `*.local.toml`, audits or downloads.
- Audits and downloads go to the caller's scratch folder (`LITERATURE_KIT_SCRATCH_DIR`). Configure an external folder, not one inside this checkout.
- Change the skill and `docs/papers-api.md` together with behaviour; reinstall the skill copies afterwards.
- Work through pull requests unless the owner says otherwise.
