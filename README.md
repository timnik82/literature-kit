# literature-kit

Project-independent scholarly literature tools for agents and people: OpenAlex, Semantic Scholar, CORE and
Europe PMC (search, identifier lookup, recommendations, available full text and supplements). Every network call made by the
command saves an audit file in the active project's scratch folder (the result's `audit_saved` says whether saving worked). This repository holds code and the agent skill only;
it contains nothing about any particular project.

## Install (once per computer)

```bash
uv sync --locked            # creates .venv; or: pip install -e . in a venv
```

Put the environment's `Scripts` folder (Windows) or `bin` folder (macOS/Linux) on PATH so `litkit` works in every project (`literature-kit` remains as an alias for now).
Clone the repository anywhere you keep tools, install once per computer, and use the same command from every project.

## Use

```bash
litkit status                       # key presence and scratch folder; no network
litkit search --provider openalex --query "..." --limit 20
litkit lookup --provider europe-pmc --id PMID:12345678
```

Details, limits and provider notes: [docs/papers-api.md](docs/papers-api.md). Per project, set
`LITERATURE_KIT_SCRATCH_DIR` for the process; API keys come from `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`
and `CORE_API_KEY` (or `[papers.*]` tables in a git-ignored `literature-kit.local.toml`; see
[literature-kit.example.toml](literature-kit.example.toml)). Europe PMC needs no key.

## Agent skill

[skills/literature-api-toolbox](skills/literature-api-toolbox/SKILL.md): copy the folder into the agent's skills
directory (`~/.agents/skills`, `~/.claude/skills`).

## Tests

```bash
uv run pytest
```
