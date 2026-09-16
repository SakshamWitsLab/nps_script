"""Matching: map DROP-sheet targets to rows in ``documents``."""

from collections import Counter
from dataclasses import dataclass, field

from config import Config
from db import (
    create_url_targets,
    fetch_active_chunks,
    fetch_chunk_stats,
    fetch_document_candidates,
    fetch_related_docs,
    fetch_url_matches,
)
from excel_reader import ExcelData
from normalizer import file_names_match, normalize_url


@dataclass
class TargetMiss:
    normalized: str
    originals: list[str] = field(default_factory=list)


@dataclass
class DetectResult:
    # URL side
    url_targets_used: int = 0
    url_normalized_targets: int = 0
    url_doc_matches: list[dict] = field(default_factory=list)
    url_matched_norms: set[str] = field(default_factory=set)
    url_misses: list[TargetMiss] = field(default_factory=list)
    # File side
    file_targets_used: int = 0
    file_doc_matches: list[dict] = field(default_factory=list)
    file_matched_originals: set[str] = field(default_factory=set)
    file_misses: list[str] = field(default_factory=list)
    # Union + expansion
    matched_ids: list = field(default_factory=list)          # all rows that will be removed
    expansion_ids: list = field(default_factory=list)        # added via supersedes/children
    chunk_stats: dict = field(default_factory=dict)

    @property
    def url_ids(self) -> list:
        return [r["id"] for r in self.url_doc_matches]

    @property
    def file_ids(self) -> list:
        return [r["id"] for r in self.file_doc_matches]

    def status_breakdown(self) -> dict:
        statuses = Counter()
        types = Counter()
        parents = 0
        superseded = 0
        for r in self.url_doc_matches + self.file_doc_matches:
            statuses[r["status"]] += 1
            types[r["source_type"]] += 1
            if r.get("is_parent"):
                parents += 1
            if r.get("superseded_by_document_id"):
                superseded += 1
        return {
            "by_status": statuses,
            "by_type": types,
            "is_parent_rows": parents,
            "superseded_rows": superseded,
        }


@dataclass
class PostCheck:
    url_active_remaining: list[dict] = field(default_factory=list)
    url_all_present: list[dict] = field(default_factory=list)   # includes soft-deleted
    file_active_remaining: list[dict] = field(default_factory=list)
    file_all_present: list[dict] = field(default_factory=list)
    chunk_leftovers: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.url_active_remaining
            or self.file_active_remaining
            or self.chunk_leftovers
        )


class Matcher:
    def __init__(self, conn, cfg: Config):
        self.conn = conn
        self.cfg = cfg

    # ------------------------------------------------------------------ detect
    def detect(self, excel: ExcelData, log=None) -> DetectResult:
        res = DetectResult()

        # ---- URLs --------------------------------------------------
        pairs = [(t.normalized, t.original) for t in excel.url_targets if t.normalized]
        create_url_targets(self.conn, pairs)
        res.url_targets_used = len(excel.url_targets)
        res.url_normalized_targets = len(excel.distinct_url_norms)

        url_rows = fetch_url_matches(self.conn, self.cfg)
        res.url_doc_matches = url_rows
        res.url_matched_norms = {r["matched_norm"] for r in url_rows}

        # misses (normalized targets with no DB row)
        norm_originals: dict[str, list[str]] = {}
        for t in excel.url_targets:
            norm_originals.setdefault(t.normalized, []).append(t.original)
        res.url_misses = [
            TargetMiss(norm, norm_originals[norm])
            for norm in sorted(norm_originals)
            if norm and norm not in res.url_matched_norms
        ]

        # ---- Files -------------------------------------------------
        res.file_targets_used = len(excel.file_targets)
        candidates = fetch_document_candidates(self.conn, self.cfg, ["DOCUMENT"])
        file_hits: list[dict] = []
        file_hit_norms: set[str] = set()
        for row in candidates:
            for t in excel.file_targets:
                if file_names_match(row["document_name"], t.original, self.cfg):
                    file_hits.append(row)
                    file_hit_norms.add(row["document_name"])
                    break
        res.file_doc_matches = file_hits
        res.file_matched_originals = file_hit_norms
        matched_targets = {
            t.original
            for t in excel.file_targets
            if any(
                file_names_match(r["document_name"], t.original, self.cfg)
                for r in candidates
            )
        }
        res.file_misses = [
            t.original for t in excel.file_targets if t.original not in matched_targets
        ]

        # ---- Union + expansion --------------------------------------
        base_ids: set = {r["id"] for r in url_rows}
        base_ids |= {r["id"] for r in file_hits}
        if log:
            log.debug("base matched ids = %d", len(base_ids))

        expanded: dict[str, dict] = {}
        frontier = set(base_ids)
        for _ in range(50):
            added: list[dict] = []
            if self.cfg.include_supersedes:
                added += fetch_related_docs(self.conn, self.cfg, list(frontier), "supersedes_document_id")
                added += fetch_related_docs(self.conn, self.cfg, list(frontier), "superseded_by_document_id")
            if self.cfg.purge_orphan_children:
                added += fetch_related_docs(self.conn, self.cfg, list(frontier), "parent_document_id")
            new_ids = set()
            for row in added:
                if row["id"] not in base_ids and row["id"] not in expanded:
                    expanded[row["id"]] = row
                    new_ids.add(row["id"])
            if not new_ids:
                break
            frontier = new_ids

        res.expansion_ids = list(expanded)
        res.matched_ids = sorted(base_ids | set(expanded))
        res.chunk_stats = fetch_chunk_stats(self.conn, res.matched_ids)
        return res

    # -------------------------------------------------------------- post-check
    def post_check(self, excel: ExcelData) -> PostCheck:
        pc = PostCheck()

        # URL rows still present / active
        pairs = [(t.normalized, t.original) for t in excel.url_targets if t.normalized]
        create_url_targets(self.conn, pairs)
        pc.url_all_present = fetch_url_matches(
            self.conn, self.cfg, extra_where="", skip_already_deleted=False
        )
        pc.url_active_remaining = [
            r for r in pc.url_all_present
            if r["deleted_at"] is None and r["status"] != "TRASHED"
        ]

        # File rows still present / active
        candidates = fetch_document_candidates(
            self.conn, self.cfg, ["DOCUMENT"], skip_already_deleted=False
        )
        file_all, file_active = [], []
        for row in candidates:
            if any(
                file_names_match(row["document_name"], t.original, self.cfg)
                for t in excel.file_targets
            ):
                file_all.append(row)
                if row["deleted_at"] is None and row["status"] != "TRASHED":
                    file_active.append(row)
        pc.file_all_present = file_all
        pc.file_active_remaining = file_active

        # Retrievable chunks still carrying a dropped name
        url_norms = excel.distinct_url_norms
        buckets = {"URL": [], "DOCUMENT": []}
        for chunk in fetch_active_chunks(self.conn):
            src = chunk["source_type"]
            if src == "URL":
                if normalize_url(chunk["doc_name"], self.cfg) in url_norms:
                    buckets["URL"].append((chunk, "chunk.doc_name still matches a dropped URL"))
            elif src == "DOCUMENT":
                if any(
                    file_names_match(chunk["doc_name"], t.original, self.cfg)
                    for t in excel.file_targets
                ):
                    buckets["DOCUMENT"].append((chunk, "chunk.doc_name still matches a dropped file"))
        for chunk_list in buckets.values():
            for chunk, reason in chunk_list:
                r = dict(chunk)
                r["reason"] = reason
                pc.chunk_leftovers.append(r)
        return pc