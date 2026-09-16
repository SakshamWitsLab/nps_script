"""Apply the deletion (hard or soft) in batches with a progress indicator.

Deletion is *chunk-identity aware*: the caller passes a
:class:`chunk_plan.ChunkPlan` that says which chunks match the DROP sheets (by
``doc_name``) and how surviving chunks must be reparented away from containers
that are about to be removed. This prevents the FK cascade from tearing out
chunks that belong to KEEP pages.
"""

import logging
import time
from typing import Sequence

from config import Config
from db import (
    batch,
    delete_chunks,
    recalc_chunks_count,
    reparent_chunks,
    soft_delete_chunks,
)

try:
    from tqdm import tqdm as _tqdm
except ImportError:  # pragma: no cover - tqdm is optional in reqs
    _tqdm = None


class DeleteStats:
    def __init__(self):
        self.mode: str = ""
        self.documents_affected: int = 0
        self.chunks_affected: int = 0
        self.chunks_reparented: int = 0
        self.batches: int = 0
        self.duration_s: float = 0.0

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "documents_affected": self.documents_affected,
            "chunks_affected": self.chunks_affected,
            "chunks_reparented": self.chunks_reparented,
            "batches": self.batches,
            "duration_seconds": round(self.duration_s, 3),
        }


def _progress(seq, desc: str, total: int):
    if _tqdm is not None:
        return _tqdm(seq, desc=desc, total=total, unit="batch")
    return seq


def _id_of(row):
    return row["id"] if isinstance(row, dict) else row[0]


def _delete_returning(conn, sql: str, params: list) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_id_of(r) for r in cur.fetchall()]


def _hard_delete(conn, ids: Sequence, cfg: Config, stats: DeleteStats, log) -> None:
    """Hard-delete rows without tripping the ``idx_docs_current_url`` unique index.

    ``documents.superseded_by_document_id`` is ``ON DELETE SET NULL``. Deleting a
    row that a *remaining* row points at would promote that remaining row to
    "current" and can collide with an existing current row in the partial unique
    index. We therefore delete in waves: each wave removes only rows that no
    remaining row points at (i.e. the oldest un-superseded versions), so no
    promotion can ever create a second current row with the same resource_path.

    By the time this runs, all surviving chunks have been reparented and all
    DROP chunks deleted, so the ``document_chunks`` FK cascade is a no-op.
    """
    remaining = set(ids)
    max_waves = len(remaining) + 100
    wave = 0
    while remaining:
        wave += 1
        if wave > max_waves:  # safety net against a non-shrinking loop
            raise RuntimeError(
                f"Hard delete stalled after {wave} waves with {len(remaining)} "
                "rows still present"
            )
        remaining_list = list(remaining)
        deleted = _delete_returning(
            conn,
            "DELETE FROM documents d "
            "WHERE d.id = ANY(%s) "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM documents c "
            "  WHERE c.superseded_by_document_id = d.id "
            "    AND c.id = ANY(%s)"
            ") RETURNING d.id",
            [remaining_list, remaining_list],
        )
        if not deleted:
            # No progress possible (cycle / external reference): force the rest.
            log.warning(
                "Hard delete: no removals in wave %d; deleting the %d "
                "remaining row(s) unconditionally.", wave, len(remaining),
            )
            deleted = _delete_returning(
                conn, "DELETE FROM documents WHERE id = ANY(%s) RETURNING id",
                [remaining_list],
            )
        stats.documents_affected += len(deleted)
        stats.batches = wave
        remaining -= set(deleted)
        log.info("Hard delete wave %d: removed %d row(s), %d remaining.",
                 wave, len(deleted), len(remaining))


def delete(conn, cfg: Config, plan, log: logging.Logger) -> DeleteStats:
    """Delete/soft-delete the planned documents and chunks.

    Progress is only committed at the very end; on error the whole run is
    rolled back by the caller.
    """
    stats = DeleteStats()
    stats.mode = cfg.delete_mode
    t0 = time.monotonic()

    drop_doc_ids = sorted(set(plan.drop_doc_ids))
    drop_chunk_ids = list(plan.drop_chunk_ids)
    log.info(
        "Deleting %d document row(s) / %d chunk(s) in mode=%s "
        "(transaction held until end)",
        len(drop_doc_ids), len(drop_chunk_ids), cfg.delete_mode,
    )

    # STEP 1 - reparent surviving chunks off documents we are about to remove.
    if plan.reparent:
        stats.chunks_reparented = reparent_chunks(conn, plan.reparent, cfg.batch_size)
        log.info("Reparented %d surviving chunk(s) onto their own documents.",
                 stats.chunks_reparented)

    # STEP 2 - drop the chunks whose doc_name matches a DROP target.
    if cfg.delete_mode == "hard":
        stats.chunks_affected = delete_chunks(conn, drop_chunk_ids, cfg.batch_size)
    else:
        stats.chunks_affected = soft_delete_chunks(
            conn, drop_chunk_ids, cfg.chunk_set_is_current, cfg.batch_size
        )
    log.info("Removed/soft-deleted %d chunk(s) by identity.", stats.chunks_affected)

    # STEP 3 - remove the DROP documents (FK cascade now has no survivors).
    if cfg.delete_mode == "hard":
        _hard_delete(conn, drop_doc_ids, cfg, stats, log)
    elif cfg.delete_mode == "soft":
        batches = list(batch(drop_doc_ids, cfg.batch_size))
        stats.batches = len(batches)
        for batch_ids in _progress(batches, "delete(soft)", total=len(batches)):
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET deleted_at = now(), status = 'TRASHED' "
                    "WHERE id = ANY(%s)",
                    [list(batch_ids)],
                )
                stats.documents_affected += cur.rowcount
    else:  # pragma: no cover - validated at load time
        raise ValueError(f"Unknown DELETE_MODE: {cfg.delete_mode}")

    # STEP 4 - keep the denormalized counter consistent on new owners.
    owners = sorted({d for _, d in plan.reparent})
    if owners:
        recalc_chunks_count(conn, owners, cfg.batch_size)

    conn.commit()
    stats.duration_s = time.monotonic() - t0
    log.info(
        "Delete complete: %d documents, %d chunks removed, %d chunks reparented "
        "in %.1fs",
        stats.documents_affected,
        stats.chunks_affected,
        stats.chunks_reparented,
        stats.duration_s,
    )
    return stats
