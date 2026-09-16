#!/usr/bin/env python3
"""KEEP verification - confirm every KEEP-sheet target is still in the DB.

Usage:
    python check_keep.py                 # uses ./.env
    python check_keep.py --env .env
    python check_keep.py --show-config
    python check_keep.py --no-disjoint   # skip the KEEP vs DROP overlap check

Exit code is 0 only when every KEEP target is present and retrievable (and, by
default, does not overlap the DROP sheets).
"""

import argparse
import logging
import sys

import config as config_mod
import db as db_mod
from keep_checker import KeepChecker
from logger import SectionLog, setup_logging
from excel_reader import read_excel, read_keep
import reporter


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NPS KEEP verification (check-report)")
    p.add_argument("--env", default=None, help="path to a .env file")
    p.add_argument("--no-disjoint", action="store_true",
                   help="skip the KEEP vs DROP overlap check")
    p.add_argument("--baseline-env", default=None,
                   help="path to a .env holding the pristine baseline DB "
                        "(BASELINE_DATABASE_URL or PG_*; overrides config)")
    p.add_argument("--no-baseline", action="store_true",
                   help="skip the chunk-regression comparison against a baseline")
    p.add_argument("--show-config", action="store_true",
                   help="print the active configuration and exit")
    return p


def _baseline_conninfo(args, cfg) -> str:
    """Resolve the baseline connection string from --baseline-env or the config."""
    if args.baseline_env:
        from dotenv import dotenv_values

        values = dotenv_values(args.baseline_env)
        url = (values.get("BASELINE_DATABASE_URL") or "").strip()
        if url:
            return url
        name = (values.get("PG_DATABASE") or values.get("DB_NAME") or "").strip()
        if name:
            return (
                f"host={values.get('PG_HOST') or values.get('DB_HOST') or 'localhost'} "
                f"port={values.get('PG_PORT') or values.get('DB_PORT') or '5432'} "
                f"dbname={name} "
                f"user={values.get('PG_USER') or values.get('DB_USER') or ''} "
                f"password={values.get('PG_PASSWORD') or values.get('DB_PASSWORD') or ''}"
            )
        return ""
    return cfg.baseline_conninfo()


def _conn_label(conn: str) -> str:
    if "/" in conn:
        return conn.rsplit("/", 1)[-1]
    for part in conn.split():
        if part.startswith("dbname="):
            return part.split("=", 1)[1]
    return conn or "(unknown)"


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    cfg = config_mod.load_config(args.env)

    if args.show_config:
        print(config_mod.print_summary(cfg))
        return 0

    errors = cfg.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("Fix the .env / environment and retry. See .env.example.")
        return 2

    out_dir = reporter.make_output_dir(cfg)
    log: logging.Logger = setup_logging(cfg, log_dir=out_dir)
    section = SectionLog(log)

    log.info("NPS KEEP verification starting (host=%s db=%s)",
             cfg.db_host or "(from DATABASE_URL)", cfg.db_name or "(from DATABASE_URL)")
    for line in config_mod.print_summary(cfg).splitlines():
        log.info("  %s", line)

    try:
        section.step("Read KEEP sheets",
                     f"{cfg.xlsx_path} -> {cfg.sheet_urls_keep!r} / {cfg.sheet_docs_keep!r}")
        keep = read_keep(cfg)
        log.info("Parsed %d KEEP URL targets and %d KEEP file targets.",
                 len(keep.url_targets), len(keep.file_targets))
        if not keep.url_targets and not keep.file_targets:
            log.error("No KEEP targets could be read from the workbook. Aborting.")
            return 3

        drop = None
        if not args.no_disjoint:
            drop = read_excel(cfg)

        baseline_conninfo = "" if args.no_baseline else _baseline_conninfo(args, cfg)
        baseline_conn = None
        if baseline_conninfo:
            try:
                baseline_conn = db_mod.connect_url(baseline_conninfo)
                log.info("Baseline DB for chunk comparison: %s",
                         _conn_label(baseline_conninfo))
            except Exception:
                log.warning("Could not connect to baseline DB %r - chunk regression "
                            "check will be report-only.", baseline_conninfo)
                baseline_conn = None

        section.step("Connect to PostgreSQL")
        conn = db_mod.connect(cfg)
        try:
            stats = db_mod.table_stats(conn)
            log.info("DB snapshot: %s documents (%s soft-deleted), %s chunks (%s active)",
                     stats["documents_total"]["documents"],
                     stats["documents_total"]["soft_deleted"],
                     stats["chunks_total"]["chunks"],
                     stats["chunks_total"]["active_chunks"])

            section.step("Check KEEP targets against the database")
            result = KeepChecker(conn, cfg, baseline_conn=baseline_conn).check(keep, drop)
            conn.rollback()
        finally:
            conn.close()
            if baseline_conn is not None:
                baseline_conn.close()

        section.step("Write check-report")
        md, js, csv_path = reporter.write_check(cfg, keep, result, out_dir)

        uc, fc = result.url_counts, result.file_counts
        log.info("")
        log.info("KEEP verification summary:")
        log.info("  URL  targets: %d  (active=%d, chunks_lost=%d, inactive=%d, missing=%d)",
                 sum(uc.values()), uc.get("PRESENT_ACTIVE", 0),
                 uc.get("CHUNKS_LOST", 0), uc.get("PRESENT_INACTIVE", 0),
                 uc.get("MISSING", 0))
        log.info("  FILE targets: %d  (active=%d, chunks_lost=%d, inactive=%d, missing=%d)",
                 sum(fc.values()), fc.get("PRESENT_ACTIVE", 0),
                 fc.get("CHUNKS_LOST", 0), fc.get("PRESENT_INACTIVE", 0),
                 fc.get("MISSING", 0))
        log.info("  Matched documents: %d", result.matched_documents)
        ct, ca = result.chunks(result.url_results + result.file_results)
        log.info("  KEEP chunks by doc_name: total=%d active=%d%s", ct, ca,
                 " (baseline=%d)" % result.baseline_chunks(
                     result.url_results + result.file_results)
                 if result.baseline_used else "")
        if drop is not None:
            log.info("  KEEP/DROP overlaps: URLs=%d files=%d",
                     len(result.drop_overlap_urls), len(result.drop_overlap_files))
        log.info("")
        if result.ok:
            log.info("VERIFICATION PASSED - every KEEP target is present and retrievable.")
        else:
            log.warning("VERIFICATION FAILED - see check_report.md for details.")
        log.info("Reports: %s", ", ".join(str(x) for x in (md, js, csv_path)))
        return 0 if result.ok else 1
    except KeyboardInterrupt:
        log.warning("Interrupted.")
        return 130
    except Exception:
        log.exception("KEEP verification failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
