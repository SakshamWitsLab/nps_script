"""Verify that every KEEP-sheet target is still present *and retrievable*.

A KEEP target must survive in **both** tables:

* ``documents``        - the page/file metadata row (matched by ``document_name``);
* ``document_chunks``  - the actual embedded chunks (matched by ``doc_name``,
  because ``document_id`` points at a coarse container document, not the page).

Classification per KEEP spreadsheet entry:

* ``PRESENT_ACTIVE``   - an active document row exists AND (it had no chunks in
                         the baseline OR it still has active chunks).
* ``CHUNKS_LOST``      - the document row is active, but chunks that existed in
                         the pristine baseline are gone.
* ``PRESENT_INACTIVE`` - matching document rows exist but all are soft-deleted/TRASHED.
* ``MISSING``          - no matching document row at all.

The check can also assert that the KEEP and DROP sheets are disjoint (no page
is both kept and dropped).
"""

from dataclasses import dataclass, field

from config import Config
from db import (
    create_url_targets,
    fetch_all_chunks,
    fetch_document_candidates,
    fetch_url_matches,
)
from excel_reader import ExcelData
from normalizer import file_accepted_forms, file_names_match, normalize_url

PRESENT_ACTIVE = "PRESENT_ACTIVE"
PRESENT_INACTIVE = "PRESENT_INACTIVE"
CHUNKS_LOST = "CHUNKS_LOST"
MISSING = "MISSING"

_ALL_STATES = (PRESENT_ACTIVE, CHUNKS_LOST, PRESENT_INACTIVE, MISSING)

_URL = "URL"
_FILE = "FILE"


@dataclass
class KeepMatch:
    id: str
    document_name: str
    status: str
    version: object
    deleted_at: object

    @property
    def active(self) -> bool:
        return self.deleted_at is None and self.status != "TRASHED"


@dataclass
class KeepTargetResult:
    kind: str
    original: str
    normalized: str
    section: str = ""
    originals: list[str] = field(default_factory=list)
    state: str = MISSING
    matches: list[KeepMatch] = field(default_factory=list)
    chunks_by_name_total: int = 0
    chunks_by_name_active: int = 0
    baseline_chunks: int | None = None

    @property
    def active_matches(self) -> list[KeepMatch]:
        return [m for m in self.matches if m.active]

    @property
    def document_active(self) -> bool:
        return any(m.active for m in self.matches)

    @property
    def chunks_ok(self) -> bool:
        if self.baseline_chunks is None:
            return True
        return not (self.baseline_chunks > 0 and self.chunks_by_name_active == 0)


@dataclass
class KeepCheckResult:
    url_results: list[KeepTargetResult] = field(default_factory=list)
    file_results: list[KeepTargetResult] = field(default_factory=list)
    drop_overlap_urls: list[str] = field(default_factory=list)
    drop_overlap_files: list[str] = field(default_factory=list)
    baseline_used: bool = False

    def counts(self, results: list[KeepTargetResult]) -> dict:
        out = {s: 0 for s in _ALL_STATES}
        for r in results:
            out[r.state] = out.get(r.state, 0) + 1
        return out

    @property
    def url_counts(self) -> dict:
        return self.counts(self.url_results)

    @property
    def file_counts(self) -> dict:
        return self.counts(self.file_results)

    def chunks(self, results: list[KeepTargetResult]) -> tuple[int, int]:
        total = sum(r.chunks_by_name_total for r in results)
        active = sum(r.chunks_by_name_active for r in results)
        return total, active

    def baseline_chunks(self, results: list[KeepTargetResult]) -> int:
        return sum((r.baseline_chunks or 0) for r in results)

    @property
    def matched_documents(self) -> int:
        return sum(len(r.matches) for r in self.url_results + self.file_results)

    @property
    def chunk_regressions(self) -> list[KeepTargetResult]:
        return [r for r in self.url_results + self.file_results if r.state == CHUNKS_LOST]

    @property
    def ok(self) -> bool:
        return (
            all(r.state == PRESENT_ACTIVE for r in self.url_results + self.file_results)
            and not self.drop_overlap_urls
            and not self.drop_overlap_files
        )


def _to_match(row: dict) -> KeepMatch:
    return KeepMatch(
        id=str(row["id"]),
        document_name=row["document_name"],
        status=row["status"],
        version=row.get("version"),
        deleted_at=row.get("deleted_at"),
    )


def aggregate_chunks(chunks: list[dict], cfg: Config) -> tuple[dict, dict]:
    """Group chunk counts by identity: URL norm and non-URL ``doc_name``."""
    url_agg: dict[str, list] = {}
    file_agg: dict[str, list] = {}
    for c in chunks:
        active = 0 if c["is_deleted"] else 1
        if c["source_type"] == "URL":
            norm = normalize_url(c["doc_name"], cfg)
            v = url_agg.setdefault(norm, [0, 0])
        else:
            v = file_agg.setdefault(c["doc_name"], [0, 0])
        v[0] += 1
        v[1] += active
    return url_agg, file_agg


def _classify(doc_state: str, baseline: int | None, current_active: int) -> str:
    if doc_state != PRESENT_ACTIVE:
        return doc_state
    if baseline is None:
        return PRESENT_ACTIVE
    if baseline > 0 and current_active == 0:
        return CHUNKS_LOST
    return PRESENT_ACTIVE


class KeepChecker:
    def __init__(self, conn, cfg: Config, baseline_conn=None):
        self.conn = conn
        self.cfg = cfg
        self.url_agg, self.file_agg = aggregate_chunks(fetch_all_chunks(conn), cfg)
        if baseline_conn is not None:
            self.base_url_agg, self.base_file_agg = aggregate_chunks(
                fetch_all_chunks(baseline_conn), cfg
            )
        else:
            self.base_url_agg = self.base_file_agg = None

    # ---------------------------------------------------------------- helpers
    def _url_chunk_counts(self, norms, baseline: bool) -> tuple[int, int]:
        agg = self.base_url_agg if baseline else self.url_agg
        if agg is None:
            return 0, 0
        total = active = 0
        for n in set(norms):
            if not n:
                continue
            v = agg.get(n)
            if v:
                total += v[0]
                active += v[1]
        return total, active

    def _file_chunk_counts(self, target: str, baseline: bool) -> tuple[int, int]:
        agg = self.base_file_agg if baseline else self.file_agg
        if agg is None:
            return 0, 0
        total = active = 0
        for doc_name, v in agg.items():
            if file_names_match(doc_name, target, self.cfg):
                total += v[0]
                active += v[1]
        return total, active

    # ---------------------------------------------------------------- check
    def check(self, keep: ExcelData, drop: ExcelData | None = None) -> KeepCheckResult:
        res = KeepCheckResult(baseline_used=self.base_url_agg is not None)
        self._check_urls(keep, res)
        self._check_files(keep, res)
        if drop is not None:
            self._check_disjoint(keep, drop, res)
        return res

    # ---------------------------------------------------------------- urls
    def _check_urls(self, keep: ExcelData, res: KeepCheckResult) -> None:
        pairs = [(t.normalized, t.original) for t in keep.url_targets if t.normalized]
        create_url_targets(self.conn, pairs)
        matched = fetch_url_matches(self.conn, self.cfg, skip_already_deleted=False)

        by_norm: dict[str, list[dict]] = {}
        for row in matched:
            by_norm.setdefault(row["matched_norm"], []).append(row)

        # Group the example/canonical values back into their spreadsheet row.
        # A KEEP entry counts as present when *any* of its candidate values
        # matches (the canonical alias often drops a '/web/pfrda/' infix).
        entries: dict[int, dict] = {}
        for t in keep.url_targets:
            if not t.normalized:
                continue
            e = entries.setdefault(t.row, {"example": None, "canonical": None,
                                           "section": t.section})
            if t.is_canonical:
                e["canonical"] = t
            else:
                e["example"] = t
            if t.section and not e["section"]:
                e["section"] = t.section

        for row_no in sorted(entries):
            e = entries[row_no]
            candidates = [t for t in (e["example"], e["canonical"]) if t]
            primary = e["example"] or e["canonical"]
            rows: list[dict] = []
            seen: set = set()
            for t in candidates:
                for r in by_norm.get(t.normalized, []):
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        rows.append(r)
            matches = [_to_match(r) for r in rows]
            norms = [t.normalized for t in candidates]
            c_total, c_active = self._url_chunk_counts(norms, baseline=False)
            b_total, _ = self._url_chunk_counts(norms, baseline=True)

            if not rows:
                doc_state = MISSING
            elif any(m.active for m in matches):
                doc_state = PRESENT_ACTIVE
            else:
                doc_state = PRESENT_INACTIVE
            baseline = b_total if self.base_url_agg is not None else None
            state = _classify(doc_state, baseline, c_active)

            res.url_results.append(
                KeepTargetResult(
                    _URL, primary.original, primary.normalized, e["section"],
                    [t.original for t in candidates], state, matches,
                    chunks_by_name_total=c_total, chunks_by_name_active=c_active,
                    baseline_chunks=baseline,
                )
            )

    # --------------------------------------------------------------- files
    def _check_files(self, keep: ExcelData, res: KeepCheckResult) -> None:
        candidates = fetch_document_candidates(
            self.conn, self.cfg, ["DOCUMENT"], skip_already_deleted=False
        )
        for t in keep.file_targets:
            rows = [
                c for c in candidates
                if file_names_match(c["document_name"], t.original, self.cfg)
            ]
            matches = [_to_match(r) for r in rows]
            c_total, c_active = self._file_chunk_counts(t.original, baseline=False)
            b_total, _ = self._file_chunk_counts(t.original, baseline=True)

            if not rows:
                doc_state = MISSING
            elif any(m.active for m in matches):
                doc_state = PRESENT_ACTIVE
            else:
                doc_state = PRESENT_INACTIVE
            baseline = b_total if self.base_file_agg is not None else None
            state = _classify(doc_state, baseline, c_active)

            res.file_results.append(
                KeepTargetResult(
                    _FILE, t.original, t.original.strip(), t.section,
                    [t.original], state, matches,
                    chunks_by_name_total=c_total, chunks_by_name_active=c_active,
                    baseline_chunks=baseline,
                )
            )

    # ---------------------------------------------------------- disjointness
    def _check_disjoint(self, keep: ExcelData, drop: ExcelData,
                        res: KeepCheckResult) -> None:
        res.drop_overlap_urls = sorted(
            keep.distinct_url_norms & (drop.distinct_url_norms if drop else set())
        )
        drop_file_forms: set[str] = set()
        for t in drop.file_targets:
            drop_file_forms |= file_accepted_forms(t.original, self.cfg)
        overlaps = []
        for t in keep.file_targets:
            if file_accepted_forms(t.original, self.cfg) & drop_file_forms:
                overlaps.append(t.original)
        res.drop_overlap_files = sorted(set(overlaps))
