"""Report generation: human-readable Markdown + machine-readable JSON + CSV."""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from config import Config
from excel_reader import ExcelData
from matcher import DetectResult, PostCheck
from db import table_stats


# --------------------------------------------------------------------------
# output dir
# --------------------------------------------------------------------------

def make_output_dir(cfg: Config) -> Path:
    if cfg.timestamped_reports:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = cfg.output_dir / stamp
    else:
        out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    return out


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _line(*parts) -> str:
    return " | ".join(str(p) if p is not None else "" for p in parts)


def _table(headers, rows, indent: int = 2) -> str:
    pad = " " * indent
    out = [pad + _line(*headers)]
    out.append(pad + _line(*["-" * max(6, len(str(h))) for h in headers]))
    for r in rows:
        out.append(pad + _line(*r))
    return "\n".join(out)


def _originals_for_norm(excel: ExcelData) -> dict[str, list[str]]:
    m: dict[str, list[str]] = {}
    for t in excel.url_targets:
        m.setdefault(t.normalized, []).append(t.original)
    return m


# --------------------------------------------------------------------------
# PRE report
# --------------------------------------------------------------------------

def pre_report_md(cfg: Config, excel: ExcelData, res: DetectResult) -> str:
    norm2o = _originals_for_norm(excel)
    breakdown = res.status_breakdown()
    uid = len(set(res.url_ids))
    fid = len(set(res.file_ids))
    total_chunks = sum(s["total"] for s in res.chunk_stats.values())
    active_chunks = sum(s["active"] for s in res.chunk_stats.values())

    lines = []
    A = lines.append
    A("# Pre-delete report")
    A("")
    A(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- Workbook: `{cfg.xlsx_path}`")
    A(f"- URL sheet: `{cfg.sheet_urls}` | file sheet: `{cfg.sheet_docs}`")
    A(f"- Delete mode: `{cfg.delete_mode}` | DRY_RUN: `{cfg.dry_run}`")
    A("")
    A("## Workbook targets")
    A("")
    A(f"- URL rows in sheet: `{excel.url_rows_total}` (skipped empty: `{excel.url_rows_skipped}`)")
    A(f"- URL target values: `{res.url_targets_used}` "
      f"(distinct normalized: `{res.url_normalized_targets}`) "
      f"[example_url={len([t for t in excel.url_targets if not t.is_canonical])}, "
      f"canonical={(res.url_targets_used - len([t for t in excel.url_targets if not t.is_canonical]))}]")
    A(f"- File rows in sheet: `{excel.file_rows_total}` (skipped empty: `{excel.file_rows_skipped}`)")
    A(f"- File target values: `{res.file_targets_used}`")
    A("")
    A("## Detected in database")
    A("")
    A(f"- URL documents matched: **{uid}**")
    A(f"- DOCUMENT rows matched: **{fid}**")
    A(f"- Total documents to remove (after expansion): **{len(res.matched_ids)}** "
      f"(expanded via supersedes/children: **{len(res.expansion_ids)}**)")
    A(f"- Attached chunks: total **{total_chunks}**, active **{active_chunks}**")
    A("")
    A("### Breakdown by status / source type (matched rows)")
    A("")
    A(_table(
        ["status", "count"],
        sorted(breakdown["by_status"].items()),
    ))
    A("")
    A("Matched rows by source type: "
      + ", ".join(f"{k}={v}" for k, v in sorted(breakdown["by_type"].items())))
    A("")
    A(f"Rows that are parent docs: `{breakdown['is_parent_rows']}` | "
      f"rows superseded at match time: `{breakdown['superseded_rows']}`")
    A("")
    A("## Targets with no database match (informational)")
    A("")
    url_misses = res.url_misses
    A(f"- URL targets with no match: **{len(url_misses)}**")
    if url_misses:
        shown = url_misses[:20]
        A("")
        A(_table(
            ["#", "normalized target", "source values"],
            [(i + 1, m.normalized, ", ".join(m.originals[:3]))
             for i, m in enumerate(shown)],
        ))
        if len(url_misses) > 20:
            A("")
            A(f"  ... and {len(url_misses) - 20} more (see JSON report).")
    A("")
    A(f"- File targets with no match: **{len(res.file_misses)}**")
    if res.file_misses:
        shown = res.file_misses[:20]
        A("")
        A(_table(
            ["#", "file target"],
            [(i + 1, f) for i, f in enumerate(shown)],
        ))
        if len(res.file_misses) > 20:
            A("")
            A(f"  ... and {len(res.file_misses) - 20} more (see JSON report).")
    A("")
    return "\n".join(lines)


def pre_report_json(cfg: Config, excel: ExcelData, res: DetectResult) -> dict:
    url_misses = [
        {"normalized": m.normalized, "originals": m.originals} for m in res.url_misses
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workbook": str(cfg.xlsx_path),
        "delete_mode": cfg.delete_mode,
        "dry_run": cfg.dry_run,
        "targets": {
            "url_rows_total": excel.url_rows_total,
            "url_rows_skipped": excel.url_rows_skipped,
            "url_target_values": res.url_targets_used,
            "url_distinct_normalized": res.url_normalized_targets,
            "file_rows_total": excel.file_rows_total,
            "file_rows_skipped": excel.file_rows_skipped,
            "file_target_values": res.file_targets_used,
        },
        "detected": {
            "url_documents": len(set(res.url_ids)),
            "file_documents": len(set(res.file_ids)),
            "total_documents_to_remove": len(res.matched_ids),
            "expansion_ids": len(res.expansion_ids),
            "chunks_total": sum(s["total"] for s in res.chunk_stats.values()),
            "chunks_active": sum(s["active"] for s in res.chunk_stats.values()),
            "by_status": dict(res.status_breakdown()["by_status"]),
            "by_type": dict(res.status_breakdown()["by_type"]),
        },
        "matched_documents": [
            {
                "id": str(r["id"]),
                "document_name": r["document_name"],
                "source_type": r["source_type"],
                "status": r["status"],
                "version": r["version"],
                "is_parent": bool(r.get("is_parent")),
                "superseded_by": str(r["superseded_by_document_id"]) if r.get("superseded_by_document_id") else None,
                "chunks_total": res.chunk_stats.get(r["id"], {}).get("total", 0),
                "chunks_active": res.chunk_stats.get(r["id"], {}).get("active", 0),
            }
            for r in res.url_doc_matches + res.file_doc_matches
        ],
        "url_targets_not_found": url_misses,
        "file_targets_not_found": res.file_misses,
    }


# --------------------------------------------------------------------------
# POST report
# --------------------------------------------------------------------------

def post_report_md(cfg: Config, excel: ExcelData, post: PostCheck, del_stats, stats_before) -> str:
    lines = []
    A = lines.append
    A("# Post-delete verification report")
    A("")
    A(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- Delete mode: `{cfg.delete_mode}`")
    A(f"- Documents affected: **{del_stats.documents_affected}** "
      f"| chunks affected: **{del_stats.chunks_affected}** "
      f"| batches: **{del_stats.batches}** "
      f"| duration: **{del_stats.duration_s:.1f}s**")
    A("")
    A("## Re-check after delete")
    A("")
    A(_table(
        ["check", "count"],
        [
            ("URL rows still present (any state)", len(post.url_all_present)),
            ("URL rows still ACTIVE (not deleted / not TRASHED)", len(post.url_active_remaining)),
            ("File rows still present (any state)", len(post.file_all_present)),
            ("File rows still ACTIVE (not deleted / not TRASHED)", len(post.file_active_remaining)),
            ("Active chunks still carrying a dropped name", len(post.chunk_leftovers)),
        ],
    ))
    A("")
    status = "PASS - nothing of the DROP list is still retrievable." if post.ok else \
        "FAIL - leftover rows found. See remaining_after_delete.csv"
    A(f"**Result: {status}**")
    if cfg.delete_mode == "soft" and (post.url_all_present or post.file_all_present):
        A("")
        A("Note: DELETE_MODE=soft keeps the rows but marks them TRASHED / "
          "chunks deleted, so they are expected to still be present yet not "
          "retrievable by the RAG. Set INCLUDE_SOFT_DELETED_IN_LEFTOVERS=true "
          "to also list them in the leftover CSV.")
    A("")
    # optional db snapshot after
    A("## Database snapshot at end")
    A("")
    docs = stats_before.get("documents_total", {}) if stats_before.get("documents_total") else None
    if docs:
        A(f"- documents total: **{docs['documents']}** (links {docs['urls']}, "
          f"docs {docs['docs']}, soft-deleted {docs['soft_deleted']})")
    chk = stats_before.get("chunks_total", {})
    if chk:
        A(f"- chunks total: **{chk['chunks']}** (active {chk['active_chunks']})")
    A("")
    return "\n".join(lines)


def post_report_json(cfg: Config, post: PostCheck, del_stats) -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "delete_mode": cfg.delete_mode,
        "deletion": del_stats.as_dict(),
        "verification": {
            "url_rows_present": len(post.url_all_present),
            "url_rows_active": len(post.url_active_remaining),
            "file_rows_present": len(post.file_all_present),
            "file_rows_active": len(post.file_active_remaining),
            "active_chunks_leftover": len(post.chunk_leftovers),
            "pass": bool(post.ok),
        },
    }


# --------------------------------------------------------------------------
# CSV exports
# --------------------------------------------------------------------------

REMAINDER_COLUMNS = [
    "source_kind", "sheet_column", "target_original", "target_normalized",
    "db_document_id", "document_name", "source_type", "status", "version",
    "deleted_at", "reason",
]


def _url_target_originals(excel, norm: str) -> str:
    for t in excel.url_targets:
        if t.normalized == norm:
            return t.original
    return norm


def write_remaining_csv(cfg: Config, excel: ExcelData, post: PostCheck, out_dir: Path) -> Path:
    rows: list[list] = []
    seen = set()

    def dedupe(key: tuple) -> bool:
        if key in seen:
            return False
        seen.add(key)
        return True

    for r in post.url_active_remaining + (
        post.url_all_present if cfg.include_soft_deleted_in_leftovers else []
    ):
        key = ("url", r["id"])
        if not dedupe(key):
            continue
        rows.append([
            "URL", "Example full URL / Canonical page",
            _url_target_originals(excel, r["matched_norm"]), r["matched_norm"],
            str(r["id"]), r["document_name"], r["source_type"], r["status"],
            r["version"], r["deleted_at"],
            "URL document still matched after deletion",
        ])

    for r in post.file_active_remaining + (
        post.file_all_present if cfg.include_soft_deleted_in_leftovers else []
    ):
        key = ("file", r["id"])
        if not dedupe(key):
            continue
        rows.append([
            "FILE", cfg.col_file_name, r["document_name"],
            r["document_name"].strip(),
            str(r["id"]), r["document_name"], r["source_type"], r["status"],
            r["version"], r["deleted_at"],
            "File document still matched after deletion",
        ])

    for r in post.chunk_leftovers:
        key = ("chunk", r["chunk_id"])
        if not dedupe(key):
            continue
        rows.append([
            "CHUNK", "document_chunks.doc_name",
            r["doc_name"], r["doc_name"].strip(),
            str(r.get("document_id")) if r.get("document_id") else "",
            r.get("doc_document_name") or "", r.get("doc_source_type") or "",
            r.get("doc_status") or "", "", r.get("doc_deleted_at") or "",
            r.get("reason", "chunk still active"),
        ])

    path = out_dir / "remaining_after_delete.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(REMAINDER_COLUMNS)
        writer.writerows(rows)
    return path


def write_matched_audit_csv(cfg: Config, res: DetectResult, out_dir: Path) -> Path:
    path = out_dir / "matched_documents.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "id", "document_name", "source_type", "status", "version",
            "is_parent", "supersedes_document_id", "superseded_by_document_id",
            "chunks_total", "chunks_active",
        ])
        for r in res.url_doc_matches + res.file_doc_matches:
            writer.writerow([
                r["id"], r["document_name"], r["source_type"], r["status"],
                r["version"], r["is_parent"],
                r.get("supersedes_document_id"),
                r.get("superseded_by_document_id"),
                res.chunk_stats.get(r["id"], {}).get("total", 0),
                res.chunk_stats.get(r["id"], {}).get("active", 0),
            ])
    return path


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def write_pre(cfg, excel, res, out_dir) -> tuple[Path, Path]:
    md = out_dir / "pre_report.md"
    js = out_dir / "pre_report.json"
    md.write_text(pre_report_md(cfg, excel, res), encoding="utf-8")
    js.write_text(
        json.dumps(pre_report_json(cfg, excel, res), indent=2, default=str),
        encoding="utf-8",
    )
    return md, js


def write_post(cfg, excel, post, del_stats, stats_after, out_dir) -> tuple[Path, Path]:
    md = out_dir / "post_report.md"
    js = out_dir / "post_report.json"
    md.write_text(
        post_report_md(cfg, excel, post, del_stats, stats_after), encoding="utf-8"
    )
    js.write_text(
        json.dumps(post_report_json(cfg, post, del_stats), indent=2, default=str),
        encoding="utf-8",
    )
    return md, js