"""PostgreSQL access layer (psycopg 3).

Matching URLs is done fully inside PostgreSQL: the DROP sheet URLs are
normalized in Python and loaded into a temporary table, then joined against the
``documents`` table using the *same* normalization expression (see
``normalizer.sql_normalize_url_expr``).

File names are matched in Python because the strategy (exact / URL-decoded /
case-insensitive) is applied over a small ``DOCUMENT`` candidate set.
"""

from typing import Iterable, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from config import Config
from normalizer import sql_normalize_url_expr


def connect(cfg: Config) -> psycopg.Connection:
    conn = psycopg.connect(cfg.db_conninfo(), row_factory=dict_row)
    # Our matching reads use the same connection/transaction as the temp tables.
    conn.autocommit = False
    return conn


def connect_url(url: str) -> psycopg.Connection:
    """Open a second connection (e.g. to the pristine baseline database)."""
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.autocommit = False
    return conn


def batch(seq: Sequence | set, size: int) -> Iterator[list]:
    items = list(seq)
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------------------------------------------------------------------
# Temporary target table + URL matching
# --------------------------------------------------------------------------

def create_url_targets(conn, pairs: Iterable[tuple[str, str]]) -> None:
    """Create/replace the temp table holding normalized URL targets.

    ``pairs`` are (normalized, first_original) tuples. Duplicates are skipped.
    """
    seen: set[str] = set()
    unique = []
    for norm, original in pairs:
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append((norm, original))

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _url_targets")
        cur.execute(
            "CREATE TEMP TABLE _url_targets (norm text NOT NULL, original text NOT NULL)"
        )
        with cur.copy("COPY _url_targets (norm, original) FROM STDIN") as copy:
            for norm, original in unique:
                copy.write_row((norm, original))


def url_match_select(cfg: Config, extra_where: str = "", skip_already_deleted: bool | None = None) -> str:
    where = ["d.source_type = 'URL'"]
    if cfg.status_filter:
        where.append(f"d.status = ANY(%s)")
    skip_deleted = cfg.skip_already_deleted if skip_already_deleted is None else skip_already_deleted
    if skip_deleted:
        where.append("d.deleted_at IS NULL")
    if extra_where:
        where.append(extra_where)
    return (
        "SELECT d.id, d.document_name, d.source_type, d.status, d.version, "
        "       d.deleted_at, d.parent_document_id, d.is_parent, "
        "       d.supersedes_document_id, d.superseded_by_document_id, "
        "       d.chunks_count, d.created_at, d.updated_at, "
        f"       t.norm AS matched_norm, t.original AS matched_target "
        f"FROM documents d "
        f"JOIN _url_targets t ON t.norm = {sql_normalize_url_expr(cfg, 'd.document_name')} "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY d.document_name"
    )


def fetch_url_matches(conn, cfg: Config, extra_where: str = "",
                      skip_already_deleted: bool | None = None) -> list[dict]:
    sql = url_match_select(cfg, extra_where, skip_already_deleted)
    params: list = []
    if cfg.status_filter:
        params.append(list(cfg.status_filter))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_document_candidates(conn, cfg: Config, source_types: Sequence[str],
                              skip_already_deleted: bool | None = None) -> list[dict]:
    where = ["d.source_type = ANY(%s)"]
    if cfg.status_filter:
        where.append("d.status = ANY(%s)")
    skip_deleted = cfg.skip_already_deleted if skip_already_deleted is None else skip_already_deleted
    if skip_deleted:
        where.append("d.deleted_at IS NULL")
    sql = (
        "SELECT d.id, d.document_name, d.source_type, d.status, d.version, "
        "       d.deleted_at, d.parent_document_id, d.is_parent, "
        "       d.supersedes_document_id, d.superseded_by_document_id, "
        "       d.chunks_count, d.created_at, d.updated_at "
        f"FROM documents d WHERE {' AND '.join(where)} "
        "ORDER BY d.document_name"
    )
    params: list = [list(source_types)]
    if cfg.status_filter:
        params.append(list(cfg.status_filter))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_related_docs(conn, cfg: Config, ids: Sequence, linked_column: str) -> list[dict]:
    """Rows whose ``linked_column`` points at one of the given ids."""
    if not ids:
        return []
    sql = (
        "SELECT d.id, d.document_name, d.source_type, d.status, d.version, "
        "       d.deleted_at, d.parent_document_id, d.is_parent, "
        "       d.supersedes_document_id, d.superseded_by_document_id, d.chunks_count "
        f"FROM documents d WHERE d.{linked_column} = ANY(%s)"
    )
    with conn.cursor() as cur:
        cur.execute(sql, [list(ids)])
        return cur.fetchall()


def fetch_chunk_stats(conn, doc_ids: Sequence) -> dict:
    """Per document: total chunks and active (not deleted / current-on) chunks."""
    if not doc_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document_id, "
            "       count(*) AS total, "
            "       count(*) FILTER (WHERE is_deleted = false) AS active, "
            "       count(*) FILTER (WHERE is_deleted = false AND is_current = true) AS active_current "
            "FROM document_chunks WHERE document_id = ANY(%s) GROUP BY document_id",
            [list(doc_ids)],
        )
        return {row["document_id"]: row for row in cur.fetchall()}


def fetch_active_chunks(conn) -> list[dict]:
    """Every retrievable chunk joined with its document metadata."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id AS chunk_id, c.document_id, c.doc_name, c.source_type, "
            "       c.is_deleted, c.is_current, "
            "       d.document_name AS doc_document_name, d.status AS doc_status, "
            "       d.deleted_at AS doc_deleted_at, d.source_type AS doc_source_type "
            "FROM document_chunks c "
            "LEFT JOIN documents d ON d.id = c.document_id "
            "WHERE c.is_deleted = false "
            "ORDER BY c.source_type, c.doc_name"
        )
        return cur.fetchall()


def fetch_all_chunks(conn) -> list[dict]:
    """Every chunk row with the columns needed to plan by ``doc_name``."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, document_id, doc_name, source_type, is_deleted, is_current "
            "FROM document_chunks"
        )
        return cur.fetchall()


def fetch_document_owner_rows(conn) -> list[dict]:
    """Minimal ``documents`` projection used to pick reparent owners."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, document_name, source_type, status, deleted_at FROM documents"
        )
        return cur.fetchall()


def reparent_chunks(conn, pairs: Sequence[tuple], batch_size: int = 1000) -> int:
    """Point chunks at a new ``document_id``.

    ``pairs`` are ``(chunk_id, new_document_id)``; the SQL parameter order is
    swapped internally to match ``SET document_id = %s WHERE id = %s``.
    """
    pairs = list(pairs)
    if not pairs:
        return 0
    affected = 0
    for part in batch(pairs, batch_size):
        rows = [(doc_id, chunk_id) for chunk_id, doc_id in part]
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE document_chunks SET document_id = %s WHERE id = %s", rows
            )
            affected += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return affected


def delete_chunks(conn, ids: Sequence, batch_size: int = 1000) -> int:
    """Hard-delete chunks by id."""
    ids = list(ids)
    if not ids:
        return 0
    affected = 0
    for part in batch(ids, batch_size):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE id = ANY(%s)", [list(part)])
            affected += cur.rowcount
    return affected


def soft_delete_chunks(conn, ids: Sequence, set_is_current: bool = False,
                       batch_size: int = 1000) -> int:
    """Mark chunks deleted by id."""
    ids = list(ids)
    if not ids:
        return 0
    if set_is_current:
        sql = ("UPDATE document_chunks SET is_deleted = true, is_current = false "
               "WHERE id = ANY(%s) AND is_deleted = false")
    else:
        sql = ("UPDATE document_chunks SET is_deleted = true "
               "WHERE id = ANY(%s) AND is_deleted = false")
    affected = 0
    for part in batch(ids, batch_size):
        with conn.cursor() as cur:
            cur.execute(sql, [list(part)])
            affected += cur.rowcount
    return affected


def recalc_chunks_count(conn, doc_ids: Sequence, batch_size: int = 500) -> None:
    """Refresh the denormalized ``documents.chunks_count`` for the given docs."""
    doc_ids = list(doc_ids)
    for part in batch(doc_ids, batch_size):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents d SET chunks_count = COALESCE(("
                "  SELECT count(*) FROM document_chunks c WHERE c.document_id = d.id"
                "), 0) WHERE d.id = ANY(%s)",
                [list(part)],
            )


def table_stats(conn) -> dict:
    """Row counts snapshot for the before/after reports."""
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_type, status, count(*) AS n "
            "FROM documents GROUP BY source_type, status ORDER BY source_type, status"
        )
        out["documents_by_type_status"] = cur.fetchall()

        cur.execute(
            "SELECT source_type, count(*) AS n, "
            "       count(*) FILTER (WHERE is_deleted = false) AS active "
            "FROM document_chunks GROUP BY source_type ORDER BY source_type"
        )
        out["chunks_by_type"] = cur.fetchall()

        cur.execute(
            "SELECT count(*) AS documents, "
            "       count(*) FILTER (WHERE source_type='URL') AS urls, "
            "       count(*) FILTER (WHERE source_type='DOCUMENT') AS docs, "
            "       count(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted "
            "FROM documents"
        )
        out["documents_total"] = cur.fetchone()

        cur.execute(
            "SELECT count(*) AS chunks, "
            "       count(*) FILTER (WHERE is_deleted=false) AS active_chunks "
            "FROM document_chunks"
        )
        out["chunks_total"] = cur.fetchone()
    return out