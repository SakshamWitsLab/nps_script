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
from keep_checker import (
    CHUNKS_LOST,
    MISSING,
    PRESENT_ACTIVE,
    PRESENT_INACTIVE,
    KeepCheckResult,
    KeepTargetResult,
)


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

def pre_report_md(cfg: Config, excel: ExcelData, res: DetectResult, plan=None) -> str:
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
    A(f"- URL rows in sheet: `{excel.url_rows_total}` (skipped empty: `{excel.url_rows_skipped}`, "
      f"header-artifact rows ignored: `{excel.header_artifact_rows}`)")
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
    A(f"- Chunks attached (by container document_id): total **{total_chunks}**, "
      f"active **{active_chunks}**")
    if plan is not None:
        A("")
        A("### Chunk plan (identity = `document_chunks.doc_name`)")
        A("")
        A(f"- Chunks to delete by identity: **{plan.drop_chunks}** "
          f"(URL **{len(plan.drop_url_chunk_ids)}** / file **{len(plan.drop_file_chunk_ids)}**)")
        A(f"- KEEP chunks preserved: **{len(plan.keep_chunk_ids)}**")
        A(f"- Other (untouched) chunks preserved: **{len(plan.untouched_chunk_ids)}**")
        A(f"- Surviving chunks reparented off DROP containers: **{len(plan.reparent)}**")
        A(f"- Reparent anomalies (no surviving owner): **{len(plan.anomalies)}**")
        if plan.anomalies:
            A("")
            A(_table(
                ["chunk_id", "source_type", "doc_name", "reason"],
                [(a["chunk_id"], a["source_type"], a["doc_name"][:80], a["reason"])
                 for a in plan.anomalies[:20]],
            ))
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


def pre_report_json(cfg: Config, excel: ExcelData, res: DetectResult, plan=None) -> dict:
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
            "header_artifact_rows_ignored": excel.header_artifact_rows,
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
        "chunk_plan": plan.as_dict() if plan is not None else None,
        "chunk_plan_anomalies": plan.anomalies if plan is not None else [],
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

def write_pre(cfg, excel, res, out_dir, plan=None) -> tuple[Path, Path]:
    md = out_dir / "pre_report.md"
    js = out_dir / "pre_report.json"
    md.write_text(pre_report_md(cfg, excel, res, plan), encoding="utf-8")
    js.write_text(
        json.dumps(pre_report_json(cfg, excel, res, plan), indent=2, default=str),
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


# --------------------------------------------------------------------------
# KEEP verification report ("check-report")
# --------------------------------------------------------------------------

CHECK_CSV_COLUMNS = [
    "kind", "section", "target_original", "target_normalized", "state",
    "db_document_id", "document_name", "status", "version", "deleted_at",
    "chunks_by_name_total", "chunks_by_name_active", "baseline_chunks",
]


def _db_label(cfg: Config, field: str = "database_url") -> str:
    url = getattr(cfg, field, "") or ""
    if url:
        tail = url.rsplit("/", 1)[-1]
        return tail or f"(from {field.upper()})"
    if field != "database_url":
        return "(not set)"
    return cfg.db_name or "(unknown)"


def _state_counts_table(result: KeepCheckResult) -> str:
    uc, fc = result.url_counts, result.file_counts
    rows = []
    for state, label in (
        (PRESENT_ACTIVE, "PRESENT_ACTIVE (retrievable)"),
        (CHUNKS_LOST, "CHUNKS_LOST (doc live, chunks gone)"),
        (PRESENT_INACTIVE, "PRESENT_INACTIVE (soft-deleted/TRASHED)"),
        (MISSING, "MISSING (no DB row)"),
    ):
        rows.append((label, uc.get(state, 0), fc.get(state, 0),
                     uc.get(state, 0) + fc.get(state, 0)))
    rows.append(("TOTAL targets",
                 sum(uc.values()), sum(fc.values()),
                 sum(uc.values()) + sum(fc.values())))
    return _table(["KEEP target state", "URLs", "files", "total"], rows)


def check_report_md(cfg: Config, keep_excel: ExcelData, result: KeepCheckResult) -> str:
    lines = []
    A = lines.append
    A("# KEEP verification report (check-report)")
    A("")
    A(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    A(f"- Database: `{_db_label(cfg)}`")
    A(f"- Workbook: `{cfg.xlsx_path}`")
    A(f"- KEEP sheets: `{cfg.sheet_urls_keep}` / `{cfg.sheet_docs_keep}`")
    A("- Pass criteria: every KEEP target must have an active/retrievable document "
      "AND must not have lost chunks it had in the baseline. The KEEP sheets must "
      "not overlap the DROP sheets.")
    A("- Chunk matching is by identity (`document_chunks.doc_name`), not by the "
      "container `document_id`.")
    if result.baseline_used:
        A(f"- Baseline database: `{_db_label(cfg, 'baseline_database_url')}` "
          "(chunk regression comparison enabled)")
    else:
        A("- Baseline database: **not configured** (chunk regression check "
          "report-only; set BASELINE_DATABASE_URL to enforce it)")
    A("")
    A("## Summary")
    A("")
    A(_state_counts_table(result))
    A("")
    uc, fc = result.url_counts, result.file_counts
    total_targets = sum(uc.values()) + sum(fc.values())
    active_ok = uc.get(PRESENT_ACTIVE, 0) + fc.get(PRESENT_ACTIVE, 0)
    A(f"- KEEP URL targets: `{sum(uc.values())}` | KEEP file targets: `{sum(fc.values())}` "
      f"| total `{total_targets}`")
    A(f"- Present & retrievable: **{active_ok}** / {total_targets}")
    A(f"- Matched DB documents (all states): **{result.matched_documents}**")
    ct, ca = result.chunks(result.url_results + result.file_results)
    bt = result.baseline_chunks(result.url_results + result.file_results)
    A(f"- KEEP chunks by doc_name: total **{ct}**, active **{ca}**"
      + (f" (baseline **{bt}**)" if result.baseline_used else ""))
    regressions = result.chunk_regressions
    A(f"- Chunk regressions (chunks lost vs baseline): **{len(regressions)}**")
    A("")
    status = ("PASS - every KEEP target is present and retrievable."
              if result.ok else
              "FAIL - some KEEP targets are missing, inactive, lost chunks, or "
              "overlap the DROP list.")
    A(f"**Result: {status}**")
    A("")

    # disjointness
    A("## KEEP vs DROP disjointness")
    A("")
    A(f"- URL targets present in both KEEP and DROP: **{len(result.drop_overlap_urls)}**")
    A(f"- File targets present in both KEEP and DROP: **{len(result.drop_overlap_files)}**")
    if result.drop_overlap_urls or result.drop_overlap_files:
        A("")
        for n in result.drop_overlap_urls:
            A(f"  - URL overlap: `{n}`")
        for f in result.drop_overlap_files:
            A(f"  - File overlap: `{f}`")
    A("")

    # problem details
    for title, results in (("URL", result.url_results), ("file", result.file_results)):
        problems = [r for r in results if r.state != PRESENT_ACTIVE]
        A(f"## {title} targets needing attention ({len(problems)})")
        A("")
        if not problems:
            A(f"All {title} targets are present and retrievable.")
            A("")
            continue
        rows = []
        for i, r in enumerate(problems, 1):
            detail = "; ".join(
                f"{m.status}/{str(m.deleted_at)[:10] if m.deleted_at else 'live'}"
                for m in r.matches[:3]
            ) or "-"
            base = "?" if r.baseline_chunks is None else r.baseline_chunks
            rows.append((i, r.state, r.section, r.original, len(r.matches),
                         f"{r.chunks_by_name_active}/{r.chunks_by_name_total}",
                         f"base={base}", detail))
        A(_table(["#", "state", "section", "target", "matched",
                  "chunks(act/tot)", "baseline", "db state"], rows))
        A("")
    return "\n".join(lines)


def check_report_json(cfg: Config, keep_excel: ExcelData, result: KeepCheckResult) -> dict:
    def target_dict(r: KeepTargetResult) -> dict:
        return {
            "kind": r.kind,
            "original": r.original,
            "normalized": r.normalized,
            "section": r.section,
            "originals": r.originals,
            "state": r.state,
            "chunks_by_name_total": r.chunks_by_name_total,
            "chunks_by_name_active": r.chunks_by_name_active,
            "baseline_chunks": r.baseline_chunks,
            "matches": [
                {
                    "id": m.id,
                    "document_name": m.document_name,
                    "status": m.status,
                    "version": m.version,
                    "deleted_at": m.deleted_at,
                    "active": m.active,
                }
                for m in r.matches
            ],
        }

    ct, ca = result.chunks(result.url_results + result.file_results)
    bt = result.baseline_chunks(result.url_results + result.file_results)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": _db_label(cfg),
        "baseline_database": (_db_label(cfg, "baseline_database_url")
                              if result.baseline_used else None),
        "baseline_used": bool(result.baseline_used),
        "workbook": str(cfg.xlsx_path),
        "keep_sheets": [cfg.sheet_urls_keep, cfg.sheet_docs_keep],
        "pass": bool(result.ok),
        "summary": {
            "url_targets": sum(result.url_counts.values()),
            "file_targets": sum(result.file_counts.values()),
            "url": result.url_counts,
            "file": result.file_counts,
            "matched_documents": result.matched_documents,
            "chunks_by_name_total": ct,
            "chunks_by_name_active": ca,
            "baseline_chunks": bt if result.baseline_used else None,
            "chunk_regressions": len(result.chunk_regressions),
        },
        "disjointness": {
            "url_overlaps": result.drop_overlap_urls,
            "file_overlaps": result.drop_overlap_files,
        },
        "url_targets": [target_dict(r) for r in result.url_results],
        "file_targets": [target_dict(r) for r in result.file_results],
    }


def write_check_csv(cfg: Config, result: KeepCheckResult, out_dir: Path) -> Path:
    path = out_dir / "check_keep_targets.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CHECK_CSV_COLUMNS)
        for r in result.url_results + result.file_results:
            base = "" if r.baseline_chunks is None else r.baseline_chunks
            tail = [r.chunks_by_name_total, r.chunks_by_name_active, base]
            if not r.matches:
                writer.writerow([
                    r.kind, r.section, r.original, r.normalized, r.state,
                    "", "", "", "", "", *tail,
                ])
                continue
            for m in r.matches:
                writer.writerow([
                    r.kind, r.section, r.original, r.normalized, r.state,
                    m.id, m.document_name, m.status, m.version, m.deleted_at,
                    *tail,
                ])
    return path


def write_check(cfg: Config, keep_excel: ExcelData, result: KeepCheckResult,
                out_dir: Path) -> tuple[Path, Path, Path]:
    md = out_dir / "check_report.md"
    js = out_dir / "check_report.json"
    md.write_text(check_report_md(cfg, keep_excel, result), encoding="utf-8")
    js.write_text(
        json.dumps(check_report_json(cfg, keep_excel, result), indent=2, default=str),
        encoding="utf-8",
    )
    csv_path = write_check_csv(cfg, result, out_dir)
    return md, js, csv_path