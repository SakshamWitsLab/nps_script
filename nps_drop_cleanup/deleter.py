"""Apply the deletion (hard or soft) in batches with a progress indicator."""

import logging
import time
from typing import Sequence

from config import Config
from db import batch

try:
    from tqdm import tqdm as _tqdm
except ImportError:  # pragma: no cover - tqdm is optional in reqs
    _tqdm = None


class DeleteStats:
    def __init__(self):
        self.mode: str = ""
        self.documents_affected: int = 0
        self.chunks_affected: int = 0
        self.batches: int = 0
        self.duration_s: float = 0.0

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "documents_affected": self.documents_affected,
            "chunks_affected": self.chunks_affected,
            "batches": self.batches,
            "duration_seconds": round(self.duration_s, 3),
        }


def _progress(seq, desc: str, total: int):
    if _tqdm is not None:
        return _tqdm(seq, desc=desc, total=total, unit="batch")
    return seq


def delete(conn, cfg: Config, doc_ids: Sequence, log: logging.Logger) -> DeleteStats:
    """Delete/soft-delete the given document ids.

    Progress is only committed at the very end; on error the whole run is
    rolled back by the caller.
    """
    stats = DeleteStats()
    stats.mode = cfg.delete_mode
    t0 = time.monotonic()

    all_ids = sorted(set(doc_ids))
    batches = list(batch(all_ids, cfg.batch_size))
    stats.batches = len(batches)
    log.info(
        "Deleting %d document rows in %d batch(es) of max %d "
        "(mode=%s, transaction held until end)",
        len(all_ids), len(batches), cfg.batch_size, cfg.delete_mode,
    )

    for batch_ids in _progress(batches, f"delete({cfg.delete_mode})", total=len(batches)):
        with conn.cursor() as cur:
            if cfg.delete_mode == "soft":
                cur.execute(
                    "UPDATE documents SET deleted_at = now(), status = 'TRASHED' "
                    "WHERE id = ANY(%s)",
                    [batch_ids],
                )
                stats.documents_affected += cur.rowcount

                if cfg.chunk_set_is_current:
                    cur.execute(
                        "UPDATE document_chunks SET is_deleted = true, is_current = false "
                        "WHERE document_id = ANY(%s) AND is_deleted = false",
                        [batch_ids],
                    )
                else:
                    cur.execute(
                        "UPDATE document_chunks SET is_deleted = true "
                        "WHERE document_id = ANY(%s) AND is_deleted = false",
                        [batch_ids],
                    )
                stats.chunks_affected += cur.rowcount
            elif cfg.delete_mode == "hard":
                cur.execute(
                    "DELETE FROM documents WHERE id = ANY(%s)",
                    [batch_ids],
                )
                stats.documents_affected += cur.rowcount
            else:  # pragma: no cover - validated at load time
                raise ValueError(f"Unknown DELETE_MODE: {cfg.delete_mode}")

    conn.commit()
    stats.duration_s = time.monotonic() - t0
    log.info(
        "Delete complete: %d documents, %d chunks affected in %.1fs",
        stats.documents_affected,
        stats.chunks_affected,
        stats.duration_s,
    )
    return stats