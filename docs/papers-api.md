# Literature API tools for agents

`literature-kit` calls the official read-only OpenAlex, Semantic Scholar and
CORE REST APIs, plus the keyless Europe PMC Articles REST API. The clients are importable as `literature_kit.papers.Client`.
Python 3.11+; no additional dependencies. Install once (`uv sync` in the checkout, or `pip install -e .` in a venv)
and put the venv's `Scripts` folder on PATH; then run `literature-kit ...`.

## Europe PMC (no key or extra package)

```text
literature-kit search --provider europe-pmc --query '(biomarker AND therapy) AND OPEN_ACCESS:Y' --limit 20 --search-id SEARCH_ID
literature-kit lookup --provider europe-pmc --id PMID:12345678
literature-kit lookup --provider europe-pmc --id PMCID:PMC1234567
literature-kit lookup --provider europe-pmc --id 10.1038/s41586-020-2649-2
literature-kit fulltext --provider europe-pmc --id PMC1234567
literature-kit supplements --provider europe-pmc --id PMC1234567
```

Search uses core-format responses and automatic cursor paging up to --limit.
Lookup accepts DOI/DOI URL, PMID, numeric PMID, PMC ID or PMCID:PMCnumber.
Zero/ambiguous/mismatched results are errors; no silent source substitution.
Abstract fields can contain markup. Native field syntax belongs in --query.

Full text is JATS article XML. The returned article PMCID is checked before
saving; this does not validate scientific completeness against the PDF. ZIP
downloads include a member/size manifest and CRC validation, with no extraction.
Archives with unsafe paths, over 10,000 members or over 250 MiB uncompressed
size are rejected. XML/ZIP responses are limited to 50 MiB and never overwrite
an existing file. Figures may be included in the supplement archive.

Downloads default to `<scratch_dir>/papers-api/downloads/`. Optional --out
selects a subfolder there or an absolute path inside scratch. Output outside
scratch is rejected. Each command also writes the normal JSON audit with
source identity, file SHA-256 and size. Availability/licensing varies by paper;
missing full text or supplements is an explicit error. No main-article PDF
downloader or Markdown converter is included. Retain final adopted sources
and records in your project's document store through its own workflow.

Europe PMC requires no config entry; status shows requires_key=false.
Requests are paced 0.4 seconds apart per client as our conservative policy,
not a guaranteed provider quota. Coordinate processes sharing an IP.

## Insert keys once on each machine

Run `literature-kit status` first. It prints the selected configuration path
and whether each key is present, never its value. No API request is sent.

Create `literature-kit.local.toml` from `literature-kit.example.toml` if you have none (the older `litkit.local.toml` / `lacaixa.local.toml`
names are also read), then add these tables, substituting your keys locally. If a table already exists, edit its api_key entry rather
than adding another table. Do not replace other entries in that file.

```toml
[papers.openalex]
api_key = "PASTE_OPENALEX_KEY_HERE"

[papers.semantic-scholar]
api_key = "PASTE_SEMANTIC_SCHOLAR_KEY_HERE"

[papers.core]
api_key = "PASTE_CORE_KEY_HERE"
```

This filename is already git-ignored. Keep it outside synced document folders and never paste
real keys into shared documents, command arguments, issue text or chat.
Keys are sent only as HTTPS headers. Status checks presence, not validity.

For a configuration independent of the agent's working directory, set
`LITERATURE_KIT_CONFIG` to the absolute path of that file in the agent's environment.
Config discovery otherwise searches the current directory and parents, then
the source checkout. Use the same config for all local agents on a machine.

Alternatively set `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, and
`CORE_API_KEY` in the agent's environment. These override TOML entries.
The tools do not automatically load `.env` files. Cloud agents need their own
checkout and secrets supplied through their platform's secret/environment
settings; local files and keys do not become available to cloud agents.

Run `literature-kit status` again after editing. Keys are loaded on every
command, so TOML changes need no restart. Environment changes may require
restarting an already-running agent.

## Commands

```text
literature-kit status
literature-kit search --provider openalex --query "deep learning protein structure" --limit 20 --search-id SEARCH_ID
literature-kit search --provider openalex --query "protein structure prediction" --filter "publication_year:2020-2026" --limit 150 --search-id SEARCH_ID
literature-kit search --provider semantic-scholar --query "deep learning protein structure" --limit 20 --search-id SEARCH_ID
literature-kit search --provider core --query "deep learning protein structure" --limit 20 --search-id SEARCH_ID
literature-kit lookup --provider openalex --id "10.1038/s41586-021-03819-2"
literature-kit lookup --provider semantic-scholar --id "DOI:10.1038/s41586-021-03819-2"
literature-kit lookup --provider core --id "YOUR_CORE_WORK_ID" --fulltext
literature-kit recommend --provider semantic-scholar --id "YOUR_SEED_DOI" --limit 20 --search-id SEARCH_ID
```

SEARCH_ID is a placeholder, not an allocated search. Before a literature search, follow
the active project's search guide: check its catalogue/log for duplicates,
allocate its next search ID if it uses one, and log each exact
query/settings/result. These commands save an audit record but do not create
catalogue rows. Metadata lookup for an already known DOI is available
independently.

All network commands emit JSON and save a uniquely named audit JSON under
`<scratch_dir>/papers-api/`; this directory must be writable before calls start.
Each record contains the operation, exact input, UTC timestamp, search ID,
normalized paper records, API endpoints/parameters and original page responses.
Failures, including missing keys, save completed pages and a sanitized error when scratch is writable; failure exit code is 1. If the audit itself cannot be saved, stdout still contains JSON with audit_saved=false and an explicit error.
Do not treat partial pages in a failed run as a complete search.
Retain final reports and durable query records under the active project's
rules; the scratch JSON is not a substitute for its catalogue/log.

Searches page automatically up to `--limit` (1-1000); recommendations allow
1-500. Provider coverage and pagination limits still apply. Results are not
automatically merged across providers; use DOI and source IDs to reconcile.
OpenAlex accepts its native `--filter`; CORE accepts its own query syntax.
Semantic Scholar search here is relevance search, not its bulk Boolean API.
Recommendations use its single-seed endpoint and default recent-paper pool.

CORE lookup accepts a DOI or numeric CORE **work** ID, not an output ID. A DOI
may match multiple repository records; exact DOI matches are retained.
`--fulltext` requests work detail and includes available text; missing text is
null. Raw audit responses may contain text even without this flag. No PDF is
downloaded. OpenAlex returns content/PDF links where available; Semantic Scholar
returns abstracts and open-access PDF links where available. Full text is not
guaranteed. Source appraisal and PDF verification rules still apply.

## Reliability and limits

Requests use a 30-second timeout, per-client pacing and at most three retries
for throttling/transient HTTP/network failures. Retry-After seconds and HTTP
dates are honored; waits above 60 seconds stop with a retry-later message.
Defaults: OpenAlex 0.11 s, Semantic Scholar 1.1 s, CORE 2.1 s between calls. Interrupted HTTP body transfers are retried through the same bounded network-error path.
Pacing is synchronized across threads and clients sharing a provider/key inside one process. Separate processes still do not coordinate quotas; serialize agents sharing the same key or IP. No automatic paid top-up occurs;
API calls can consume an existing paid balance according to provider settings.
The tools do not estimate account billing or guarantee complete coverage.
Redirects are rejected to avoid forwarding authorization headers elsewhere.

Python example:

```python
from literature_kit.papers import Client
result = Client("openalex").search("protein structure prediction", limit=20)
# Client methods return dictionaries; the CLI additionally saves audit files.
```

Official references checked 2026-11-05:
- https://help.openalex.org/api/llm-quick-reference/
- https://api.semanticscholar.org/api-docs/graph
- https://api.semanticscholar.org/api-docs/recommendations
- https://core.ac.uk/services/api
- https://api.core.ac.uk/docs/v3 (browser access returned 403 during implementation;
  authenticated CORE API access was verified separately by live diagnostics, see below).


## Official OpenAlex CLI: complementary bulk route, not wrapped here

Our client calls REST directly. The provider's `openalex-official` package adds
batch metadata/PDF/TEI XML downloads with checkpoint resume and adaptive rate
limiting. It accepts OPENALEX_API_KEY. An optional adapter is a follow-up after
testing its logging, file handling and quota behavior; no package installed or
bulk content run by this change. Reference: https://help.openalex.org/access/cli/

## Verification status

Unit tests cover all clients; live metadata diagnostics succeeded for OpenAlex,
Semantic Scholar and CORE. Semantic Scholar's one-result search diagnostic
returned 429 despite pacing; do not infer a permanent limitation.
Europe PMC CLI lookup, article XML and supplement archive downloads succeeded
for a live test article: 106,293 XML bytes, 3,126,891 ZIP bytes and 13
members, saved in scratch only. No PDF completeness review was performed.
CORE `lookup --fulltext` also succeeded live after the work-detail path was
corrected (no trailing slash on `/works/{id}`); recommendations and broad
discovery queries remain untested live, and no live pagination or bulk
benchmark was performed. These checks are diagnostics, not a completed
literature evidence search.



## Audit and file-failure guarantees

Returned results contain detached audit snapshots; later calls on the same
client cannot alter prior results. Raw metadata response retention has a
64 MiB per-client aggregate cap in addition to the 50 MiB per-response cap.
Exceeding that budget stops with an explicit failure and retains earlier pages;
use a narrower query or a new client. The rejected page body is not retained.

Downloads and audit JSON are written to an exclusively created temporary file
in the destination directory, flushed, then atomically published using a
no-replace hard link. Existing files remain untouched, and failed writes leave
no partial final file. Temporary files created by the failed operation are
cleaned up when filesystem permissions allow it. Filesystems without hard-link
support report a clean save error. Validation and filesystem failures are
recorded in the download audit. If scratch itself is unavailable, an audit file
cannot be guaranteed; the CLI reports the failure as JSON on stdout.


## Shared usage skill

Use [literature-api-toolbox](../skills/literature-api-toolbox/SKILL.md) for provider selection, query
refinement, repository/version reconciliation and source checks. Copy that folder into the agent runtime skills
directory to enable discovery; keys and the literature-kit installation remain separate.

## Shared command and configuration

`literature-kit` is the project-independent entry point. After updating the checkout, re-run `uv sync`
(fallback: `pip install -e .`) so the console command matches the code.

Audits and downloads go to the active project's scratch folder. Set `LITERATURE_KIT_SCRATCH_DIR` for the
process (or `scratch_dir` in the config file selected with `LITERATURE_KIT_CONFIG`) and confirm it with
`literature-kit status` (`scratch_dir`) before any search. Do not set a global output folder. Retain adopted
sources and final records under that project's rules. Installing the skill supplies guidance, not
credentials or project paths. Catalogue rules apply only within the project that defines them.

Compatibility: `LITKIT_*` / `LACAIXA_*` environment variables and `litkit.local.toml` / `lacaixa.local.toml`
are still read as fallbacks (`LITERATURE_KIT_*` wins), so existing key files keep working.

