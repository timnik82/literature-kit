# AGENTS.md — literature-kit

Project-independent literature tools. Keep this repository free of any project's paths, document names, search
logs, credentials or catalogue rules; those belong to the project that uses the tool.

- Code: `src/literature_kit/` (`papers.py` commands and clients, `europe_pmc.py`, `config.py`). Python 3.11+, no runtime dependencies.
- Tests are offline (`uv run pytest`). Do not commit keys, `*.local.toml`, audits or downloads.
- Audits and downloads go to the caller's scratch folder (`LITERATURE_KIT_SCRATCH_DIR`). Configure an external folder, not one inside this checkout.
- Change the skill and `docs/papers-api.md` together with behaviour; reinstall the skill copies afterwards.
- Work through pull requests unless the owner says otherwise.
