"""Decide the fate of every chunk *by identity* rather than by its container.

In this schema ``document_chunks.document_id`` points at a coarse "container"
document (for example a site homepage), while the real page/file a chunk came
from is stored in ``document_chunks.doc_name``. Deleting a container therefore
cascades chunks that belong to pages we want to keep.

To avoid that, the deletion is planned as follows:

1. chunks whose ``doc_name`` matches a DROP URL / DROP file are dropped;
2. every surviving chunk still attached to a to-be-deleted document is
   *reparented* onto a surviving ``documents`` row whose ``document_name``
   matches the chunk's ``doc_name``;
3. only then are the DROP documents removed, so the FK cascade has nothing
   left to take.
"""

from dataclasses import dataclass, field

from config import Config
from db import fetch_all_chunks, fetch_document_owner_rows
from excel_reader import ExcelData
from normalizer import file_names_match, normalize_url


@dataclass
class ChunkPlan:
    drop_url_chunk_ids: list = field(default_factory=list)
    drop_file_chunk_ids: list = field(default_factory=list)
    keep_chunk_ids: list = field(default_factory=list)
    untouched_chunk_ids: list = field(default_factory=list)
    drop_doc_ids: list = field(default_factory=list)
    reparent: list = field(default_factory=list)  # [(chunk_id, new_document_id)]
    anomalies: list = field(default_factory=list)

    @property
    def drop_chunk_ids(self) -> list:
        return self.drop_url_chunk_ids + self.drop_file_chunk_ids

    @property
    def drop_chunks(self) -> int:
        return len(self.drop_url_chunk_ids) + len(self.drop_file_chunk_ids)

    @property
    def survivors(self) -> int:
        return len(self.keep_chunk_ids) + len(self.untouched_chunk_ids)

    def as_dict(self) -> dict:
        return {
            "chunks_to_drop": self.drop_chunks,
            "chunks_to_drop_url": len(self.drop_url_chunk_ids),
            "chunks_to_drop_file": len(self.drop_file_chunk_ids),
            "keep_chunks_preserved": len(self.keep_chunk_ids),
            "untouched_chunks_preserved": len(self.untouched_chunk_ids),
            "chunks_reparented": len(self.reparent),
            "reparent_anomalies": len(self.anomalies),
        }

    def summary_lines(self) -> list[str]:
        return [
            f"  Chunks to delete (by doc_name)  : {self.drop_chunks} "
            f"(URL {len(self.drop_url_chunk_ids)} / file {len(self.drop_file_chunk_ids)})",
            f"  KEEP chunks preserved           : {len(self.keep_chunk_ids)}",
            f"  Other chunks preserved          : {len(self.untouched_chunk_ids)}",
            f"  Chunks reparented off DROP docs : {len(self.reparent)}",
            f"  Reparent anomalies (would lose) : {len(self.anomalies)}",
        ]


def build_chunk_plan(conn, cfg: Config, drop: ExcelData, keep: ExcelData | None,
                     drop_doc_ids, log=None) -> ChunkPlan:
    plan = ChunkPlan()
    drop_doc_set = {str(i) for i in drop_doc_ids}

    chunks = fetch_all_chunks(conn)
    docs = fetch_document_owner_rows(conn)

    # --- indexes over *surviving* documents only -------------------------
    url_owners: dict[str, list] = {}
    doc_owners: list = []
    for r in docs:
        if str(r["id"]) in drop_doc_set:
            continue
        if r["source_type"] == "URL":
            url_owners.setdefault(normalize_url(r["document_name"], cfg), []).append(r["id"])
        else:
            doc_owners.append((r["id"], r["document_name"]))

    owner_cache: dict[str, object] = {}

    def find_owner(source_type: str, doc_name: str):
        key = f"{source_type}\x00{doc_name}"
        if key in owner_cache:
            return owner_cache[key]
        owner = None
        if source_type == "DOCUMENT":
            for did, dname in doc_owners:
                if file_names_match(dname, doc_name, cfg):
                    owner = did
                    break
        else:
            ids = url_owners.get(normalize_url(doc_name, cfg)) or []
            owner = ids[0] if ids else None
        owner_cache[key] = owner
        return owner

    drop_url_norms = drop.distinct_url_norms
    drop_file_targets = [t.original for t in drop.file_targets]
    keep_url_norms = keep.distinct_url_norms if keep else set()
    keep_file_targets = [t.original for t in keep.file_targets] if keep else []

    for c in chunks:
        cid = c["id"]
        source_type = c["source_type"]
        doc_name = c["doc_name"]

        is_drop = False
        if source_type == "URL":
            if normalize_url(doc_name, cfg) in drop_url_norms:
                plan.drop_url_chunk_ids.append(cid)
                is_drop = True
        elif source_type == "DOCUMENT":
            if any(file_names_match(doc_name, t, cfg) for t in drop_file_targets):
                plan.drop_file_chunk_ids.append(cid)
                is_drop = True

        if is_drop:
            continue

        is_keep = False
        if source_type == "URL":
            if normalize_url(doc_name, cfg) in keep_url_norms:
                is_keep = True
        elif source_type == "DOCUMENT":
            if any(file_names_match(doc_name, t, cfg) for t in keep_file_targets):
                is_keep = True
        if is_keep:
            plan.keep_chunk_ids.append(cid)
        else:
            plan.untouched_chunk_ids.append(cid)

        # A surviving chunk must not remain attached to a document we delete.
        if str(c["document_id"]) in drop_doc_set:
            owner = find_owner(source_type, doc_name)
            if owner is None:
                plan.anomalies.append(
                    {"chunk_id": str(cid), "doc_name": doc_name,
                     "source_type": source_type, "reason": "no surviving owner document"}
                )
            else:
                plan.reparent.append((cid, owner))

    plan.drop_doc_ids = [i for i in drop_doc_ids]
    if log is not None:
        for a in plan.anomalies[:20]:
            log.warning("Chunk %s (%s) has no surviving owner doc - it will be "
                        "removed with its container: %s",
                        a["chunk_id"], a["source_type"], a["doc_name"])
        if len(plan.anomalies) > 20:
            log.warning("... and %d more reparent anomalies (see pre_report.json).",
                        len(plan.anomalies) - 20)
    return plan
