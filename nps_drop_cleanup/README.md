# NPS Drop Cleanup

Deletes the URLs and documents listed under the **DROP** sheets of the triage
workbook (`NPS_RAG_Ingestion_Review_TRIAGED.xlsx`) from the RAG PostgreSQL
database.

Matching is done against `documents.document_name`:

| DROP sheet            | Column used                                   | DB rows matched                                   |
| --------------------- | --------------------------------------------- | ------------------------------------------------- |
| `DROP - URLs`         | `Example full URL` (always)                   | `documents` where `source_type = 'URL'`           |
| `DROP - URLs`         | `Canonical page (...)` (when flag on)         | `documents` where `source_type = 'URL'`           |
| `DROP - Documents`    | `File name`                                   | `documents` where `source_type = 'DOCUMENT'`      |

Chunks (`document_chunks`) are removed **by identity**, not by their container.
In this database all chunks hang off a handful of container documents (the site
homepages), while the real page/file is stored in `document_chunks.doc_name`.
Naively deleting a container therefore cascades away chunks belonging to KEEP
pages. Instead the tool:

1. deletes chunks whose `doc_name` matches a DROP URL / DROP file;
2. **reparents** every surviving chunk still attached to a to-be-deleted
   container onto a surviving `documents` row whose `document_name` matches the
   chunk's `doc_name`;
3. then removes the DROP document rows (so the FK cascade has nothing left).

`KEEP - URLs` / `KEEP - Documents` are read to protect their chunks, and chunks
that are in neither sheet are preserved too.

---

## Install

```bash
cd ~/Downloads/nps_script/nps_drop_cleanup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Prepare for testing against a copy

A fresh test copy avoids touching production:

```bash
createdb nps_drop_test
psql nps_drop_test < ~/Downloads/nps_script/chatbot2026-09-11\ \(19_02_12\).sql
```

```bash
cp .env.example .env
# in .env:
#   DATABASE_URL=postgresql://USER:PASS@localhost:5432/nps_drop_test
#   DB_NAME=nps_drop_test
#   (adjust user/password as needed)
```

> Requires the `vector` extension used by `document_chunks.embedding`; the dump
> contains a `CREATE EXTENSION` for it (or install via
> `pip install pgvector`).

---

## Usage

```bash
# 1. Safety first: DRY RUN (default). Matches everything, reports, changes NOTHING.
python main.py

# 2. Review output/<timestamp>/pre_report.md and matched_documents.csv.

# 3. Actually delete (still asks for a final y/N confirmation):
python main.py --apply
```

Command line options:

```
python main.py                 # dry-run by default
python main.py --apply         # real run (asks y/N)
python main.py --env /path/.env
python main.py --delete-mode hard|soft   # override DELETE_MODE
python main.py --dry-run       # force dry run
python main.py --show-config   # print active configuration and exit
python main.py --list-sheets   # list workbook sheets and exit
```

### Exit codes

| code | meaning                                     |
| ---- | ------------------------------------------- |
| 0    | success (or cancelled / nothing to do)      |
| 1    | pipeline error (nothing committed)          |
| 2    | configuration error                         |
| 3    | nothing readable from workbook              |
| 130  | interrupted (Ctrl+C, nothing committed)     |

---

## KEEP verification (`check_keep.py`)

Confirms that everything listed under `KEEP - URLs` / `KEEP - Documents` is
still present and retrievable **in both `documents` and `document_chunks`**,
and that the KEEP and DROP sheets do not overlap.

```bash
./.venv/bin/python check_keep.py              # uses ./.env
./.venv/bin/python check_keep.py --show-config
./.venv/bin/python check_keep.py --no-disjoint    # skip KEEP vs DROP overlap check
./.venv/bin/python check_keep.py --no-baseline    # skip chunk-regression compare
./.venv/bin/python check_keep.py --baseline-env /path/pristine.env
```

Chunks are matched by identity (`document_chunks.doc_name`), because
`document_id` points at a container, not the page. Each KEEP entry is
classified as:

| state | meaning |
| --- | --- |
| `PRESENT_ACTIVE` | an active document row exists and it still has active chunks (or had none in the baseline) |
| `CHUNKS_LOST` | the document row is active but chunks that existed in the baseline are gone |
| `PRESENT_INACTIVE` | matching document rows exist but all are soft-deleted/TRASHED |
| `MISSING` | no matching document row at all |

An entry counts as present when **any** of its candidate values (`Example full
URL` or `Canonical page`) matches, because the canonical alias sometimes drops a
`/web/pfrda/` path infix.

**Baseline comparison.** To detect lost chunks, point the checker at a pristine
copy via `BASELINE_DATABASE_URL` (or `--baseline-env FILE`). A target that had
chunks there but has none now becomes `CHUNKS_LOST` and fails. Without a
baseline the chunk comparison is report-only and only document presence is
enforced.

Outputs `check_report.md`, `check_report.json` and `check_keep_targets.csv`
into the same `output/<timestamp>/` directory. Exit code `0` = every KEEP
target is present & retrievable with its chunks and there is no KEEP/DROP
overlap; `1` otherwise (useful for CI). KEEP sheet names are configurable via
`SHEET_URLS_KEEP` / `SHEET_DOCS_KEEP`.

---

## What it does, step by step

1. **Read the workbook** – loads both DROP sheets using the configured column
   names; rows without a value are skipped and counted.
2. **Connect** – PostgreSQL connection from `DATABASE_URL` or `DB_*` vars.
3. **Detect** (the "how much detected" part):
   - URLs are normalized (scheme/www/query/fragment/trailing-slash aware) in
     Python, loaded into a temp table, and joined against `documents` with the
     exact same normalization applied in SQL.
   - File names match against the `DOCUMENT` rows using the selected strategy
     (`exact`, `decoded`, or `both`) and optional case sensitivity.
   - Optionally expands the id set to version chains (supersedes /
     superseded_by) and (off by default) children of matched parents.
   - **Chunk plan** – classifies every `document_chunks` row by `doc_name` into
     drop / keep / untouched and computes the reparent map (see the top section).
4. **Pre-report** – per-sheet counts, matches by status/type, the chunk plan,
   and the list of targets that had no DB match. Written as
   `pre_report.md`, `pre_report.json`, `matched_documents.csv`.
5. **Safety gate** – exits after the pre-report unless `--apply` is given, then
   still prompts `y/N`.
6. **Delete** – reparent survivors, drop the planned chunks, then remove the
   DROP documents; batched (`BATCH_SIZE`), one transaction, progress bar.
7. **Post-check** – re-runs every matching query and a chunk-level check, writes
   `post_report.md/.json` and `remaining_after_delete.csv` for anything that is
   still active.
8. **Report** – human + JSON reports land in
   `output/<timestamp>/` (or `output/` with `TIMESTAMPED_REPORTS=false`).

---

## Configuration reference (`.env`)

See `.env.example` for the full annotated list. Highlights:

| Variable                         | Default                                  | Meaning                                                        |
| -------------------------------- | ---------------------------------------- | -------------------------------------------------------------- |
| `DATABASE_URL`                   | *(empty)*                                | Full conn string; else build from `DB_*`.                     |
| `XLSX_PATH`                      | `./NPS_RAG_Ingestion_Review_TRIAGED.xlsx`| Workbook to read.                                              |
| `INCLUDE_CANONICAL_URLS`         | `true`                                   | Also use the `Canonical page` column for URL dropping.        |
| `URL_STRIP_WWW/QUERY/FRAGMENT`,<br/>`URL_STRIP_TRAILING_SLASH`, `URL_LOWERCASE` | `true` ×5 | URL normalization switches used on both Python & SQL sides.             |
| `FILE_MATCH_STRATEGY`            | `both`                                   | `exact` \| `decoded` \| `both`                                 |
| `FILE_MATCH_CASE_SENSITIVE`      | `false`                                  |                                                               |
| `DELETE_MODE`                    | `soft`                                   | `hard` → DELETE; `soft` → TRASHED + `is_deleted`.            |
| `DRY_RUN`                        | `true`                                   | No delete without `--apply`.                                  |
| `STATUS_FILTER`                  | *(empty = all)*                          | Comma list, e.g. `COMPLETED`.                                  |
| `SKIP_ALREADY_DELETED`           | `true`                                   | Don't touch rows already `TRASHED`/soft-deleted.              |
| `INCLUDE_SUPERSEDES`             | `true`                                   | Also remove version chains pointing at matched docs.          |
| `PURGE_ORPHAN_CHILDREN`          | `false`                                  | Also remove child rows whose parent got matched.              |
| `CHUNK_SET_IS_CURRENT`           | `false`                                  | In soft mode also set `is_current=false` on chunks.          |
| `INCLUDE_SOFT_DELETED_IN_LEFTOVERS` | `false`                                | Write soft-deleted rows into the leftover CSV too.            |
| `BASELINE_DATABASE_URL`          | *(empty)*                                | Pristine DB used by `check_keep.py` for chunk-regression compare. |
| `BATCH_SIZE`                     | `500`                                    | Documents per DELETE/UPDATE batch.                             |
| `OUTPUT_DIR` / `TIMESTAMPED_REPORTS` | `./output` / `true`                   | Where reports/CSVs go.                                        |

---

## Output artifacts

In `output/<timestamp>/`:

- `run.log` – full debug log.
- `pre_report.md` / `pre_report.json` – targets vs database, detection summary.
- `matched_documents.csv` – every row that would be / was deleted.
- `post_report.md` / `post_report.json` – verification results.
- `remaining_after_delete.csv` – anything from the DROP list still active after
  deletion (URLs, files, and/or chunks). Columns:
  `source_kind, sheet_column, target_original, target_normalized, db_document_id,
  document_name, source_type, status, version, deleted_at, reason`.
- `check_report.md` / `check_report.json` (from `check_keep.py`) – KEEP targets
  vs database, per-target state, and KEEP/DROP overlaps.
- `check_keep_targets.csv` – one row per KEEP target/document match (or a single
  row for a missing target). Columns:
  `kind, section, target_original, target_normalized, state, db_document_id,
  document_name, status, version, deleted_at, chunks_by_name_total,
  chunks_by_name_active, baseline_chunks`.

---

## Notes / behaviour decisions

- **Soft vs hard:** `DELETE_MODE=soft` keeps the rows (status `TRASHED`,
  `deleted_at` set, the matching chunks `is_deleted=true`) so nothing is
  retrievable by RAG while keeping an audit trail. `hard` removes them
  physically. In both modes only chunks whose `doc_name` matches a DROP target
  are touched; KEEP and unlisted chunks are reparented to surviving documents
  and preserved. The post-check always verifies *active/retrievable* leftovers;
  "present but TRASHED" rows are reported separately and only written to CSV if
  `INCLUDE_SOFT_DELETED_IN_LEFTOVERS=true`.
- **Chunk identity & reparenting:** all chunks are attached to a few container
  documents, so `document_id` is *not* the page identity — `document_chunks.doc_name`
  is. The deleter reparents surviving chunks off containers before deleting them,
  and refreshes `documents.chunks_count` on the new owners. `check_keep.py`
  verifies KEEP chunks by `doc_name` for the same reason.
- **Hard delete and version chains:** `documents.superseded_by_document_id` is
  `ON DELETE SET NULL` and a partial unique index
  (`idx_docs_current_url` on `resource_path` for current `COMPLETED` URLs) allows
  only one current version per page. A single bulk `DELETE` can transiently
  promote a middle version into that index and fail. Hard mode therefore deletes
  in **waves**, oldest un-superseded versions first, so no second current row can
  ever appear. `version` chains must be complete for this to be collision-free;
  keep `INCLUDE_SUPERSEDES=true` so the whole chain is matched.
- **Header artefacts:** a data row whose value is identical to a configured
  column header (saw this once in `DROP - URLs`) is skipped and counted in the
  pre-report as `header-artifact rows ignored`, never treated as a target.
- **URL matching** ignores protocol, `www.`, trailing slashes, query strings and
  fragments (all toggleable) so `http://www.pfrda.org.in/page` equals
  `https://pfrda.org.in/page/`.
- **File matching** compares raw and URL-decoded names (DB stores names
  URL-encoded, e.g. `PFRDA+%28Exits...%29.pdf`) case-insensitively by default.
- **Everything is env-configurable**; no code change is needed to switch DB,
  sheets, columns, matching rules, or delete mode.