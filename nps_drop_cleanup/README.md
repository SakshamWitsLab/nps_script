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

Chunks (`document_chunks`) are removed together with their document:
**hard** mode cascades via the FK, **soft** mode marks them `is_deleted=true`.

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
4. **Pre-report** – per-sheet counts, matches by status/type, attached chunk
   counts, and the list of targets that had no DB match. Written as
   `pre_report.md`, `pre_report.json`, `matched_documents.csv`.
5. **Safety gate** – exits after the pre-report unless `--apply` is given, then
   still prompts `y/N`.
6. **Delete** – batched (`BATCH_SIZE`), one transaction, progress bar.
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

---

## Notes / behaviour decisions

- **Soft vs hard:** `DELETE_MODE=soft` keeps the rows (status `TRASHED`,
  `deleted_at` set, chunks `is_deleted=true`) so nothing is retrievable by RAG
  while keeping an audit trail. `hard` removes them physically. The post-check
  always verifies *active/retrievable* leftovers; "present but TRASHED" rows are
  reported separately and only written to CSV if
  `INCLUDE_SOFT_DELETED_IN_LEFTOVERS=true`.
- **URL matching** ignores protocol, `www.`, trailing slashes, query strings and
  fragments (all toggleable) so `http://www.pfrda.org.in/page` equals
  `https://pfrda.org.in/page/`.
- **File matching** compares raw and URL-decoded names (DB stores names
  URL-encoded, e.g. `PFRDA+%28Exits...%29.pdf`) case-insensitively by default.
- **Everything is env-configurable**; no code change is needed to switch DB,
  sheets, columns, matching rules, or delete mode.