---
name: literature-api-toolbox
description: Use when an agent needs to find, check or retrieve scholarly papers efficiently with the shared literature-kit tools, in the right order, optionally combined with Firecrawl Research: discovery, DOI or PMID lookup, related-paper expansion, in-body passage checks, and available Europe PMC article text and supplements.
---

# Literature API toolbox

Use the existing `literature-kit` command instead of creating another API client. This toolbox retrieves source records; relevance, evidence quality and completeness still require judgment.

## Locate the tool

Run `literature-kit <operation> ...` from the project you are working in. It is installed once per computer from the `literature-kit` repository (`timnik82/literature-kit` on GitHub), with the environment's `Scripts` (Windows) or `bin` (macOS/Linux) folder on PATH. Where the checkout lives is a per-computer choice; the active project's own notes may say where. If the command is missing, install it from that repository (`uv sync` in the checkout, or `pip install -e .` in a venv) and add that folder to PATH. Do not write a new API client as a substitute, and do not assume installing this skill installs the command.

## Setup check 1 — path routing (always do this)

Literature commands write audits and downloads to the active project's scratch folder, so verify routing **before** any search, independently of API keys. Set `LITERATURE_KIT_SCRATCH_DIR` for the process (or `scratch_dir` in a git-ignored `literature-kit.local.toml` selected with `LITERATURE_KIT_CONFIG`) and check:

```bash
literature-kit status
```

`scratch_dir` must be the active project's scratch folder, outside synced document folders. Never set a global output folder shared across projects.

## Setup check 2 — provider keys (separate from path routing)

Separately from path routing, verify provider key presence (keys do **not** configure paths, and paths do not configure keys). The same `literature-kit status` output lists them:

It reports configuration and key presence without making an API request and never prints values. Keys come from environment variables — `OPENALEX_API_KEY` (OpenAlex), `SEMANTIC_SCHOLAR_API_KEY` (Semantic Scholar), `CORE_API_KEY` (CORE) — or from `[papers.openalex]`, `[papers.semantic-scholar]`, `[papers.core]` (`api_key`) in the `literature-kit.local.toml` file selected above. Environment values override the file. Europe PMC requires no key.

Never print key values or put them in command arguments, reports, prompts, or shared repository files. Cloud agents need their own secrets configured; installing this skill supplies none.

Read `docs/papers-api.md` in the literature-kit repository for detailed command limits and file guarantees. Use `literature-kit <operation> --help` for available arguments.

> Compatibility note: older `LITKIT_*` / `LACAIXA_*` variables and `litkit.local.toml` / `lacaixa.local.toml` files are still read as fallbacks (`LITERATURE_KIT_*` wins).

## Recommended order

Use the tools together, cheapest and most specific step first. Firecrawl Research is an optional companion for semantic discovery and passage checks (`FIRECRAWL_API_KEY`; check with `firecrawl --status`); its own documentation and skills cover its details. If it is unavailable, skip its steps and use `literature-kit` routes directly.

1. **Known paper:** go straight to step 5.
2. **Discover.** Concept questions where wording varies: `firecrawl research search-papers "<question>" --limit 20`, with several framings. Exact terms, Boolean queries or structured filters: `literature-kit search` (see the routes below).
3. **Expand** from your strongest hits, only if needed: `firecrawl research related-papers <seedIds...> --intent "<specific intent>"`, or `literature-kit recommend --provider semantic-scholar --id <seed>`.
4. **Check before fetching.** Confirm that a candidate really reports what you need: `firecrawl research read-paper <paperId> --question "<specific question>"`. Drop a candidate only when the evidence shows it does not qualify. A missing or inconclusive passage means unverified, not rejected: keep it and check another source.
5. **Resolve** the record: `literature-kit lookup --provider <openalex|europe-pmc> --id <ID>`, using the `pmid:`, `pmcid:` or `doi:` from the hit. For an arXiv-only hit: `literature-kit lookup --provider semantic-scholar --id ARXIV:<id>`.
6. **Retrieve** only what the question needs: `literature-kit fulltext --provider europe-pmc --id <PMCID>` or `supplements`.
7. **Log** queries and adopted sources under the active project's rules.

## Choose the route

| Need | Starting route | Important distinction |
|---|---|---|
| Biomedical discovery and available full text | `europe-pmc` | Native field/Boolean syntax; JATS and supplements require availability |
| Broad interdisciplinary discovery or structured filters | `openalex` | `--filter` is OpenAlex-only; content links are not downloaded automatically |
| Relevance search or related papers | `semantic-scholar` | Search here is not its bulk Boolean API; recommendations default to a recent-paper pool |
| Repository coverage or available work text | `core` | Multiple deposits/versions can describe one paper; work IDs differ from output IDs |

Choose complementary providers for the question; do not run every provider automatically. For a known paper, prefer identifier lookup over another discovery search.

## Search, reconcile, retrieve

1. Define the evidence needed: target population/model, intervention or phenomenon, measurement technique, and relevant dates. For experimental methods, distinguish live/in vitro/in vivo conditions and specific analytical modalities explicitly.
2. Check existing searches and literature records first. Follow the active project's search log, catalogue, or tracking system (e.g. a search log, spreadsheet or issue tracker) to avoid repeating identical queries. When the project tracks search IDs, pass it via `--search-id <ID>`. Example IDs in documentation are never allocations.
3. Start with a small result limit. Adapt syntax per provider; identical words do not imply comparable search semantics. Refine when hits are incidental (e.g. Europe PMC field queries like `TITLE_ABS:(biomarker AND therapy) AND OPEN_ACCESS:Y`). Title/abstract restrictions can miss full-text-only evidence. A capped result set cannot establish absence or compare recall.
4. Reconcile case-insensitive DOI and title matches before counting studies. Check article versus erratum, conference abstract, dataset DOI, and repository version. Preserve provider IDs and provenance. Do not silently merge conflicting metadata.
5. For useful hits, inspect actual abstracts or methods. Recommendations follow the seed paper's overall subject, so stop an irrelevant branch early. Retrieve only the source needed for the question.

```text
literature-kit search --provider openalex --query "deep learning protein structure" --limit 20 --search-id SEARCH_ID
literature-kit lookup --provider europe-pmc --id PMID:12345678
literature-kit lookup --provider openalex --id 10.1038/s41586-020-2649-2
literature-kit recommend --provider semantic-scholar --id 10.1038/s41586-020-2649-2 --limit 10 --search-id SEARCH_ID
literature-kit fulltext --provider europe-pmc --id PMC1234567
literature-kit supplements --provider europe-pmc --id PMC1234567
```

Replace `SEARCH_ID` with the project-allocated ID if applicable. CORE `lookup --fulltext` requests available work text; null/missing text is possible. Europe PMC downloads JATS XML and a supplement ZIP, not the main article PDF or Markdown. The ZIP can include article images; a downloaded archive is not a reviewed supplement. Use the project's PDF acquisition/conversion/validation procedure when original figures, tables, or central numerical claims are needed. Do not treat XML/OCR as verified against the original publication PDF.

For a PMC article whose website PDF route fails, its official public dataset can provide an independent PDF source. Consult the current [PMC dataset access documentation](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/) to resolve the article version and PDF location; validate PDF bytes, title/DOI and hash. Legacy PMC package routes were retired in 2026. This fallback is separate from the toolbox's implemented download commands.

## Handle failures and finish

CLI network calls emit JSON and save a unique scratch audit (`saved_to`, `audit_saved`, exact requests, raw responses). Check exit status, `error`, and audit persistence before treating a run as complete; retained pages from a failed run are partial. Returned DOI/PDF links need identity checks before adoption. Scratch audit paths are not durable catalogue entries: retain adopted outputs under project rules.

Pacing/retries are built in. Semantic Scholar requests are spaced 1.1 seconds apart in one process. Separate processes/agents sharing a key or IP must serialize work; do not assume their quotas are coordinated. Respect Retry-After/retry-later results rather than loop immediately. Existing account calls may consume quota/balance; large batches require the user's intended scope. No automatic top-up is provided.

CORE work-detail/full-text lookup uses the canonical `/works/{id}` path (no trailing slash); redirects remain rejected on principle — report any redirect failure rather than following it. Official OpenAlex bulk CLI is a separate, unwrapped route; do not imply it is implemented here.

Log each exact query, settings, and result in the active project's search catalogue or log, including failures, and deduplicate retained papers. Report what was inspected (metadata, abstract, full text, original PDF/figures), what remains unverified, and what new evidence actually adds. Follow local connector-passage logging and verification rules before citing claims.
