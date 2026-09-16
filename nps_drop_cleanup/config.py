"""Central, fully env-driven configuration.

Every value can be overridden through the process environment or an `.env` file
(passed with `--env`). Sensible defaults are provided so the tool runs out of
the box against a restored copy of the production dump.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n"}


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def env_first(names: tuple, default: str = "") -> str:
    """First non-empty env var among ``names`` (later names are fallbacks)."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def env_int_first(names: tuple, default: int) -> int:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            try:
                return int(value.strip())
            except ValueError:
                return default
    return default


@dataclass
class Config:
    # --- database ----------------------------------------------------------
    database_url: str = ""
    baseline_database_url: str = ""  # optional pristine DB for chunk regression
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    # baseline connection (used when baseline_database_url is empty)
    baseline_db_host: str = "localhost"
    baseline_db_port: int = 5432
    baseline_db_name: str = ""
    baseline_db_user: str = ""
    baseline_db_password: str = ""

    # --- input workbook ----------------------------------------------------
    xlsx_path: str = "NPS_RAG_Ingestion_Review_TRIAGED.xlsx"
    sheet_urls: str = "DROP - URLs"
    sheet_docs: str = "DROP - Documents"
    sheet_urls_keep: str = "KEEP - URLs"
    sheet_docs_keep: str = "KEEP - Documents"
    col_example_url: str = "Example full URL"
    col_canonical_url: str = "Canonical page (all locale/alias variants merged)"
    col_file_name: str = "File name"
    col_section: str = "Section"

    # --- URL matching ------------------------------------------------------
    include_canonical_urls: bool = True
    url_lowercase: bool = True
    url_strip_www: bool = True
    url_strip_trailing_slash: bool = True
    url_strip_query: bool = True
    url_strip_fragment: bool = True

    # --- file matching -----------------------------------------------------
    file_match_strategy: str = "both"  # exact | decoded | both
    file_match_case_sensitive: bool = False

    # --- deletion ----------------------------------------------------------
    delete_mode: str = "soft"  # hard | soft
    dry_run: bool = True
    batch_size: int = 500
    status_filter: tuple = ()  # empty tuple == all statuses
    skip_already_deleted: bool = True
    include_supersedes: bool = True
    purge_orphan_children: bool = False
    chunk_set_is_current: bool = False

    # --- post-delete check -------------------------------------------------
    include_soft_deleted_in_leftovers: bool = False

    # --- output ------------------------------------------------------------
    output_dir: Path = Path("./output")
    timestamped_reports: bool = True
    log_level: str = "INFO"

    # --- runtime (not from env) -------------------------------------------
    env_file: str | None = None
    _validated: bool = False

    # ------------------------------------------------------------------ util
    def db_conninfo(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password}"
        )

    def baseline_conninfo(self) -> str:
        """Connection string for the pristine baseline DB (empty if not set)."""
        if self.baseline_database_url:
            return self.baseline_database_url
        if not self.baseline_db_name:
            return ""
        return (
            f"host={self.baseline_db_host} port={self.baseline_db_port} "
            f"dbname={self.baseline_db_name} user={self.baseline_db_user} "
            f"password={self.baseline_db_password}"
        )

    @property
    def url_source_columns(self) -> list[str]:
        cols = [self.col_example_url]
        if self.include_canonical_urls:
            cols.append(self.col_canonical_url)
        return cols

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.database_url and not self.db_name:
            errors.append("No database configured: set DATABASE_URL or PG_DATABASE (+ PG_USER/PG_HOST/etc).")
        if not Path(self.xlsx_path).is_file():
            errors.append(f"XLSX_PATH does not exist: {self.xlsx_path}")
        if not Path(self.xlsx_path).suffix.lower() in (".xlsx", ".xlsm"):
            errors.append(f"XLSX_PATH is not an .xlsx file: {self.xlsx_path}")
        if self.delete_mode not in ("hard", "soft"):
            errors.append(f"DELETE_MODE must be 'hard' or 'soft', got '{self.delete_mode}'")
        if self.file_match_strategy not in ("exact", "decoded", "both"):
            errors.append(
                f"FILE_MATCH_STRATEGY must be 'exact', 'decoded' or 'both', "
                f"got '{self.file_match_strategy}'"
            )
        if self.batch_size <= 0:
            errors.append("BATCH_SIZE must be a positive integer")
        return errors


def load_config(env_file: str | None = None) -> Config:
    """Load the configuration from the environment / an `.env` file.

    When ``env_file`` is not given, a ``.env`` in the current working directory
    is loaded automatically (if present). Environment variables already
    exported by the shell take precedence over the values in the file.
    """
    candidate = env_file or (".env" if Path(".env").is_file() else None)
    if candidate:
        try:
            from dotenv import load_dotenv

            load_dotenv(candidate, override=False)
        except ImportError:
            if env_file:
                raise RuntimeError(
                    "python-dotenv is required to load an --env file. "
                    "Install dependencies first: pip install -r requirements.txt"
                )

    raw_status = env_str("STATUS_FILTER", "")
    status_filter = tuple(s.strip().upper() for s in raw_status.split(",") if s.strip())

    # Connection parts: PG_* names first, DB_* kept as backward-compatible aliases.
    db_host = env_first(("PG_HOST", "DB_HOST"), "localhost")
    db_port = env_int_first(("PG_PORT", "DB_PORT"), 5432)
    db_name = env_first(("PG_DATABASE", "DB_NAME"), "")
    db_user = env_first(("PG_USER", "DB_USER"), "")
    db_password = env_first(("PG_PASSWORD", "DB_PASSWORD"), "")

    b_host = env_first(("BASELINE_PG_HOST", "BASELINE_DB_HOST"), db_host)
    b_port = env_int_first(("BASELINE_PG_PORT", "BASELINE_DB_PORT"), db_port)
    b_name = env_first(("BASELINE_PG_DATABASE", "BASELINE_DB_NAME"), "")
    b_user = env_first(("BASELINE_PG_USER", "BASELINE_DB_USER"), db_user)
    b_password = env_first(("BASELINE_PG_PASSWORD", "BASELINE_DB_PASSWORD"), db_password)

    cfg = Config(
        database_url=env_str("DATABASE_URL", ""),
        baseline_database_url=env_str("BASELINE_DATABASE_URL", ""),
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        baseline_db_host=b_host,
        baseline_db_port=b_port,
        baseline_db_name=b_name,
        baseline_db_user=b_user,
        baseline_db_password=b_password,
        xlsx_path=env_str("XLSX_PATH", "NPS_RAG_Ingestion_Review_TRIAGED.xlsx"),
        sheet_urls=env_str("SHEET_URLS", "DROP - URLs"),
        sheet_docs=env_str("SHEET_DOCS", "DROP - Documents"),
        sheet_urls_keep=env_str("SHEET_URLS_KEEP", "KEEP - URLs"),
        sheet_docs_keep=env_str("SHEET_DOCS_KEEP", "KEEP - Documents"),
        col_example_url=env_str("COL_EXAMPLE_URL", "Example full URL"),
        col_canonical_url=env_str(
            "COL_CANONICAL_URL", "Canonical page (all locale/alias variants merged)"
        ),
        col_file_name=env_str("COL_FILE_NAME", "File name"),
        col_section=env_str("COL_SECTION", "Section"),
        include_canonical_urls=env_bool("INCLUDE_CANONICAL_URLS", True),
        url_lowercase=env_bool("URL_LOWERCASE", True),
        url_strip_www=env_bool("URL_STRIP_WWW", True),
        url_strip_trailing_slash=env_bool("URL_STRIP_TRAILING_SLASH", True),
        url_strip_query=env_bool("URL_STRIP_QUERY", True),
        url_strip_fragment=env_bool("URL_STRIP_FRAGMENT", True),
        file_match_strategy=env_str("FILE_MATCH_STRATEGY", "both").strip().lower(),
        file_match_case_sensitive=env_bool("FILE_MATCH_CASE_SENSITIVE", False),
        delete_mode=env_str("DELETE_MODE", "soft").strip().lower(),
        dry_run=env_bool("DRY_RUN", True),
        batch_size=env_int("BATCH_SIZE", 500),
        status_filter=status_filter,
        skip_already_deleted=env_bool("SKIP_ALREADY_DELETED", True),
        include_supersedes=env_bool("INCLUDE_SUPERSEDES", True),
        purge_orphan_children=env_bool("PURGE_ORPHAN_CHILDREN", False),
        chunk_set_is_current=env_bool("CHUNK_SET_IS_CURRENT", False),
        include_soft_deleted_in_leftovers=env_bool(
            "INCLUDE_SOFT_DELETED_IN_LEFTOVERS", False
        ),
        output_dir=Path(env_str("OUTPUT_DIR", "./output")),
        timestamped_reports=env_bool("TIMESTAMPED_REPORTS", True),
        log_level=env_str("LOG_LEVEL", "INFO").strip().upper(),
        env_file=candidate,
        _validated=True,
    )
    return cfg


def print_summary(cfg: Config) -> str:
    """Human readable, env-level summary of the active configuration."""
    conn = cfg.database_url or (
        f"{cfg.db_user}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"
    )
    lines = [
        "Configuration:",
        f"  DB (target)             : {conn}",
        f"  xlsx                    : {cfg.xlsx_path}",
        f"  URL sheet  / col        : {cfg.sheet_urls!r} / {cfg.col_example_url!r}",
        f"  Canonical col (flag={cfg.include_canonical_urls}): {cfg.col_canonical_url!r}",
        f"  File sheet / col        : {cfg.sheet_docs!r} / {cfg.col_file_name!r}",
        f"  KEEP sheets             : {cfg.sheet_urls_keep!r} / {cfg.sheet_docs_keep!r}",
        f"  URL normalization       : lowercase={cfg.url_lowercase} strip_www={cfg.url_strip_www} "
        f"strip_query={cfg.url_strip_query} strip_fragment={cfg.url_strip_fragment} "
        f"strip_slash={cfg.url_strip_trailing_slash}",
        f"  File match strategy     : {cfg.file_match_strategy} "
        f"(case_sensitive={cfg.file_match_case_sensitive})",
        f"  DELETE_MODE             : {cfg.delete_mode}",
        f"  DRY_RUN                 : {cfg.dry_run}",
        f"  BATCH_SIZE              : {cfg.batch_size}",
        f"  STATUS_FILTER           : {','.join(cfg.status_filter) or '<all>'}",
        f"  SKIP_ALREADY_DELETED    : {cfg.skip_already_deleted}",
        f"  INCLUDE_SUPERSEDES      : {cfg.include_supersedes}",
        f"  PURGE_ORPHAN_CHILDREN   : {cfg.purge_orphan_children}",
        f"  CHUNK_SET_IS_CURRENT    : {cfg.chunk_set_is_current}",
        f"  INCLUDES soft in leftovers CSV: {cfg.include_soft_deleted_in_leftovers}",
    ]
    baseline = cfg.baseline_conninfo()
    if baseline:
        lines.append(f"  DB (baseline)           : {baseline}")
    return "\n".join(lines)