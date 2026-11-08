---
name: literature-api-toolbox
description: Use when an agent needs to find, check or retrieve scholarly papers efficiently with the shared literature-kit tools, in the right order, optionally combined with Firecrawl Research, for discovery, DOI or PMID lookup, related-paper expansion, in-body passage checks, and available Europe PMC article text and supplements.
---

# Literature API toolbox

Use the existing `litkit` command instead of creating another API client. This toolbox retrieves source records; relevance, evidence quality and completeness still require judgment.

## Locate the tool

Run `litkit <operation> ...` from the project you are working in. It is installed once per computer from the `litkit` repository (`timnik82/literature-kit` on GitHub), with the environment's `Scripts` (Windows) or `bin` (macOS/Linux) folder on PATH. Where the checkout lives is a per-computer choice; the active project's own notes may say where. If the command is missing, install it from that repository (`uv sync` in the checkout, or `pip install -e .` in a venv) and add that folder to PATH. Do not write a new API client as a substitute, and do not assume installing this skill installs the command.

## Setup check 1 — path routing (always do this)

Literature commands write audits and downloads to the active project's scratch folder, so verify routing **before** any search, independently of API keys. Set `LITERATURE_KIT_SCRATCH_DIR` for the process (or `scratch_dir` in a git-ignored `literature-kit.local.toml` selected with `LITERATURE_KIT_CONFIG`) and check:

```bash
litkit status
```

`scratch_dir` must be the active project's scratch folder, outside synced document folders. Never set a global output folder shared across projects.

## Setup check 2 — provider keys (separate from path routing)

Separately from path routing, verify provider key presence (keys do **not** configure paths, and paths do not configure keys). The same `litkit status` output lists them:

It reports configuration and key presence without making an API request and never prints values. Keys come from environment variables — `OPENALEX_API_KEY` (OpenAlex), `SEMANTIC_SCHOLAR_API_KEY` (Semantic Scholar), `CORE_API_KEY` (CORE) — or from `[papers.openalex]`, `[papers.semantic-scholar]`, `[papers.core]` (`api_key`) in the `literature-kit.local.toml` file selected above. Environment values override the file. Europe PMC requires no key.

Never print key values or put them in command arguments, reports, prompts, or shared repository files. Cloud agents need their own secrets configured; installing this skill supplies none.

Read `docs/papers-api.md` in the literature-kit repository for detailed command limits and file guarantees. Use `litkit <operation> --help` for available arguments.

> Compatibility note: older `LITKIT_*` / `LACAIXA_*` variables and `litkit.local.toml` / `lacaixa.local.toml` files are still read as fallbacks (`LITERATURE_KIT_*` wins).

## Recommended order

Use the tools together, cheapest and most specific step first. Firecrawl Research is an optional companion for semantic discovery and passage checks (`FIRECRAWL_API_KEY`; check with `firecrawl --status`); its own documentation and skills cover its details. If it is unavailable, skip its steps and use `litkit` routes directly.

1. **Known paper:** go straight to step 5.
2. **Discover.** Concept questions where wording varies: `firecrawl research search-papers "<question>" --limit 20`, with several framings. Firecrawl Research is mostly biomedical, so for physics, chemistry, materials or engineering start with a broad semantic connector instead (see [Other connectors](#other-connectors)). Exact terms, Boolean queries or structured filters: `litkit search` (see the routes below).
3. **Expand** from your strongest hits, only if needed: `firecrawl research related-papers <seedIds...> --intent "<specific intent>"`, or `litkit recommend --provider semantic-scholar --id <seed>`. A recommendation can return 404 or nothing for a valid DOI, and it drifts in niche fields: check the first few results before reading more.
4. **Check before fetching.** Confirm that a candidate really reports what you need: `firecrawl research read-paper <paperId> --question "<specific question>"`. Drop a candidate only when the evidence shows it does not qualify. A missing or inconclusive passage means unverified, not rejected: keep it and check another source.
5. **Resolve** the record: `litkit lookup --provider <openalex|europe-pmc> --id <ID>`, using the `pmid:`, `pmcid:` or `doi:` from the hit. For an arXiv-only hit: `litkit lookup --provider semantic-scholar --id ARXIV:<id>`. `litkit` records carry no retraction field, though an OpenAlex raw response can include `is_retracted` and the audit retains it; check retraction status separately before citing (see [Other connectors](#other-connectors)).
6. **Retrieve** only what the question needs: `litkit fulltext --provider europe-pmc --id <PMCID>` or `supplements`.
7. **Log** queries and adopted sources under the active project's rules.

## Choose the route

| Need | Starting route | Important distinction |
|---|---|---|
| Biomedical discovery and available full text | `europe-pmc` | Native field/Boolean syntax; JATS and supplements require availability |
| Broad interdisciplinary discovery or structured filters | `openalex` | `--filter` is OpenAlex-only; content links are not downloaded automatically |
| Relevance search or related papers | `semantic-scholar` | Search here is not its bulk Boolean API; recommendations default to a recent-paper pool |
| Repository coverage or available work text | `core` | Multiple deposits/versions can describe one paper; work IDs differ from output IDs |

Choose complementary providers for the question; do not run every provider automatically. For a known paper, prefer identifier lookup over another discovery search.

## Other connectors

A session may also offer scholarly and web search connectors. Use the ones available; these are starting points, not a ranking for every field.

| Need | Use | Watch for |
|---|---|---|
| Semantic discovery outside biomedicine | A scholarly search taking a plain question (for example SciSpace) | Duplicate records; patents appear among papers |
| Passages, tables, conference abstracts and accepted manuscripts | A web search that returns page text (for example Exa or Tavily) | Vendor pages; confirm the identity of a paper with `lookup` |
| Retraction status and citing statements | scite `verify_papers`, or `search_literature` with `dois` | Keep `limit` near 3 and send a few DOIs per call, because full citation payloads can overflow the context. Treat any DOI with no returned status as unverified |
| Biomedical records | PubMed, Europe PMC, Firecrawl Research | Few useful hits outside life sciences |

For a new field, try one question on two or three connectors and keep those that return on-topic papers. Add any connector search to the project's log.

## Fetch, file, convert and check

Match the effort to how the paper will be used.

**Before filing.** Compare the DOI, title and SHA-256 with the project's library. A repository copy can be a paper the library already holds under another name.

**When a publisher blocks the download.** Scripted requests often get a bot page, so check for the `%PDF-` header and open the file to confirm its title. Try the PMC public dataset for PMC articles. Otherwise open the DOI link in the person's own Chrome, on an institutional network where possible, and let it save the file. A connected browser may be on another computer, so confirm the file arrived before closing the tab. Do not solve a CAPTCHA. If the article page is readable but the PDF is not, a web scraper can supply the text for reading, and the PDF can follow later.

**Reading.** For a one-off question, read the PDF's text layer or its pages directly. Superscripts, minus signs and symbols can be damaged in the text layer, so check any number you use on the rendered page.

**Converting.** Convert to Markdown only for papers kept in a library that will be searched or reused. Remove converter blocks that describe figures: their numbers are estimates, and their contents can be invented or swapped. Keep figure captions, and move them into the main text if the manuscript prints them after the references.

**Checking a conversion.** Scale it to the use:

| Use of the paper | Check |
|---|---|
| Background reading | A scripted damage and numeric sweep |
| Kept in a library | The same sweep, plus page, table and caption checks |
| Numbers will be quoted | A publisher-text cross-check where available, and those passages and tables compared with the rendered page |
| Central to a decision or a whole batch of quotes | A full agent check, one paper per agent |

A full agent check of one paper can cost about 300,000 tokens, so scope it to the pages that matter. Run the agents read-only. Their findings are leads: look at the page yourself before recording a flag as fact, and give any correction a second reader.

**Cross-checking against publisher text.** For open-access papers, the publisher's own text is a second source that does not share OCR or PDF text-layer errors. Prefer, in order:

1. JATS XML from `litkit fulltext --provider europe-pmc`. Some articles are refused because the file holds a DTD declaration; that is a safety guard, so move to the next source.
2. Publisher HTML with its tags, for example `firecrawl scrape <url> --format html --only-main-content -o <file>`. Keep `<sup>` and `<sub>` when extracting text. Publishers can block scrapers, and a manuscript-only paper may have no HTML.
3. Scraped Markdown, for reading only: it can flatten `10²¹` to `1021` and drop equations.

Run two comparisons, because each misses what the other finds:

- **Existence:** every number in the conversion must occur in the publisher text. This catches invented content such as figure tables, but misses a wrong number that also occurs elsewhere.
- **In place:** align the two word sequences (for example with `difflib.SequenceMatcher`) and flag numbers that differ at the same position, as well as aligned numeric insertions and deletions. This catches garbled ranges, omitted numbers (such as a dropped 8 in 2–8 that passes the existence check), and single-digit slips.

Normalise superscripts, minus signs and LaTeX forms first, and remove citations. Expect a few false flags from equations and formatting, and settle every flag on the rendered PDF page. In tests on three papers, the in-place comparison caught most planted digit errors with few flags per paper, and found a garbled range the existence check missed; the existence check found an invented figure table that the in-place check missed. The PDF stays the version to cite, because the web text can differ from it.

**Reading is the step that changes conclusions.** A verified conversion only protects the numbers. Compare each paper with the question at hand, and revise any lead that came from an abstract once the full text is read.

## Search, reconcile, retrieve

1. Define the evidence needed: target population/model, intervention or phenomenon, measurement technique, and relevant dates. For experimental methods, distinguish live/in vitro/in vivo conditions and specific analytical modalities explicitly.
2. Check existing searches and literature records first. Follow the active project's search log, catalogue, or tracking system (e.g. a search log, spreadsheet or issue tracker) to avoid repeating identical queries. When the project tracks search IDs, pass it via `--search-id <ID>`. Example IDs in documentation are never allocations.
3. Start with a small result limit. Adapt syntax per provider; identical words do not imply comparable search semantics. Refine when hits are incidental (e.g. Europe PMC field queries like `TITLE_ABS:(biomarker AND therapy) AND OPEN_ACCESS:Y`). Title/abstract restrictions can miss full-text-only evidence. A capped result set cannot establish absence or compare recall.
4. Reconcile case-insensitive DOI and title matches before counting studies. Check article versus erratum, conference abstract, dataset DOI, and repository version. Preserve provider IDs and provenance. Do not silently merge conflicting metadata.
5. For useful hits, inspect actual abstracts or methods. Recommendations follow the seed paper's overall subject, so stop an irrelevant branch early. Retrieve only the source needed for the question.

```text
litkit search --provider openalex --query "deep learning protein structure" --limit 20 --search-id SEARCH_ID
litkit search --provider openalex --query "protein folding" --filter "title_and_abstract.search:structure,publication_year:2020-2026" --limit 20 --search-id SEARCH_ID
litkit lookup --provider europe-pmc --id PMID:12345678
litkit lookup --provider openalex --id 10.1038/s41586-020-2649-2
litkit recommend --provider semantic-scholar --id 10.1038/s41586-020-2649-2 --limit 10 --search-id SEARCH_ID
litkit fulltext --provider europe-pmc --id PMC1234567
litkit supplements --provider europe-pmc --id PMC1234567
```

Replace `SEARCH_ID` with the project-allocated ID if applicable. OpenAlex search is lexical: keep `--query` to a few keywords. To require a term in the title or abstract, OpenAlex still accepts the legacy `title_and_abstract.search:` filter shown above, but marks the `filter=field.search:` form deprecated in favour of the `search` parameter (`search.title_and_abstract`), and both cost the same, so use the filter form only when the term must be constrained to the title or abstract. Write year limits as a range. A `>` passed through a shell, such as a Python `subprocess` call with `shell=True`, redirects the output to a file and returns nothing. CORE `lookup --fulltext` requests available work text; null/missing text is possible. Europe PMC downloads JATS XML and a supplement ZIP, not the main article PDF or Markdown. The ZIP can include article images; a downloaded archive is not a reviewed supplement. Use the project's PDF acquisition/conversion/validation procedure when original figures, tables, or central numerical claims are needed. Do not treat XML/OCR as verified against the original publication PDF.

For a PMC article whose website PDF route fails, its official public dataset can provide an independent PDF source. Consult the current [PMC dataset access documentation](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/) to resolve the article version and PDF location; validate PDF bytes, title/DOI and hash. Legacy PMC package routes were retired in 2026. This fallback is separate from the toolbox's implemented download commands.

## Handle failures and finish

CLI network calls emit JSON and save a unique scratch audit (`saved_to`, `audit_saved`, exact requests, raw responses). Check exit status, `error`, and audit persistence before treating a run as complete; retained pages from a failed run are partial. Provider records can hold keys that differ only by case, so plain `ConvertFrom-Json` can fail. In PowerShell 7.3 or later, use `ConvertFrom-Json -AsHashtable`, which preserves case-distinct keys. Windows PowerShell 5.1 lacks that switch, and PowerShell 6.0-7.2 do not preserve case-distinct keys, so parse the output with Python there. Returned DOI/PDF links need identity checks before adoption. Scratch audit paths are not durable catalogue entries: retain adopted outputs under project rules.

Pacing/retries are built in. Semantic Scholar requests are spaced 1.1 seconds apart in one process. Separate processes/agents sharing a key or IP must serialize work; do not assume their quotas are coordinated. Respect Retry-After/retry-later results rather than loop immediately. Existing account calls may consume quota/balance; large batches require the user's intended scope. No automatic top-up is provided.

CORE work-detail/full-text lookup uses the canonical `/works/{id}` path (no trailing slash); redirects remain rejected on principle — report any redirect failure rather than following it. Official OpenAlex bulk CLI is a separate, unwrapped route; do not imply it is implemented here.

Log each exact query, settings, and result in the active project's search catalogue or log, including failures, and deduplicate retained papers. Report what was inspected (metadata, abstract, full text, original PDF/figures), what remains unverified, and what new evidence actually adds. Follow local connector-passage logging and verification rules before citing claims.
