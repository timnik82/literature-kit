# literature-kit

Project-independent scholarly literature tools for agents and people: OpenAlex, Semantic Scholar, CORE and
Europe PMC (search, identifier lookup, recommendations, available full text and supplements). Every network call
saves an audit file in the active project's scratch folder. This repository holds code and the agent skill only;
it contains nothing about any particular project.

## Install (once per computer)

```bash
uv sync --locked            # creates .venv; or: pip install -e . in a venv
```

Put the environment's `Scripts` folder (`bin` on macOS/Linux) on PATH so `literature-kit` works in every project.
Clone the repository anywhere you keep tools, install once per computer, and use the same command from every project.

## Use

```bash
literature-kit status                       # key presence and scratch folder; no network
literature-kit search --provider openalex --query "..." --limit 20
literature-kit lookup --provider europe-pmc --id PMID:12345678
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
