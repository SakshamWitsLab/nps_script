"""URL and file-name normalization.

The Python implementations MUST stay in sync with the SQL expression produced
by :func:`sql_normalize_url_expr` — both are used against the DROP workbook
values and the Postgres ``documents.document_name`` column respectively.
"""

import re
from typing import Iterable
from urllib.parse import unquote_plus

from config import Config

# --------------------------------------------------------------------------
# URL normalization
# --------------------------------------------------------------------------

_SCHEME_RE = re.compile(r"^[a-zA-Z0-9+.\-]+://")
_WWW_RE = re.compile(r"^www\.")
_FRAGMENT_RE = re.compile(r"#.*")
_QUERY_RE = re.compile(r"\?.*")
_TRAILING_SLASH_RE = re.compile(r"/+$")


def normalize_url(value: str, cfg: Config) -> str:
    """Normalize a URL into the canonical key used for matching.

    Order of operations (keep in sync with ``sql_normalize_url_expr``):
    scheme removal -> www removal -> fragment removal -> query removal ->
    trailing-slash removal -> lowercase(if enabled).
    """
    if value is None:
        return ""
    s = str(value).strip().strip("\"'")
    if cfg.url_lowercase:
        s = s.lower()
    s = _SCHEME_RE.sub("", s)
    if cfg.url_strip_www:
        s = _WWW_RE.sub("", s)
    if cfg.url_strip_fragment:
        s = _FRAGMENT_RE.sub("", s)
    if cfg.url_strip_query:
        s = _QUERY_RE.sub("", s)
    if cfg.url_strip_trailing_slash:
        s = _TRAILING_SLASH_RE.sub("", s)
    return s


def sql_normalize_url_expr(cfg: Config, column: str = "document_name") -> str:
    """Postgres expression that mirrors :func:`normalize_url`.

    ``column`` is used unquoted here only because the caller passes controlled
    identifiers (never raw user input).
    """
    expr = f"({column})::text"

    def repl(e: str, pattern: str) -> str:
        return f"regexp_replace({e}, {pattern}, '')"

    expr = repl(expr, "'^[a-zA-Z0-9+.\\-]+://'")
    if cfg.url_strip_www:
        expr = repl(expr, "'^www\\.'")
    if cfg.url_strip_fragment:
        expr = repl(expr, "'#.*'")
    if cfg.url_strip_query:
        expr = repl(expr, "'\\?.*'")
    if cfg.url_strip_trailing_slash:
        expr = repl(expr, "'/+$'")
    if cfg.url_lowercase:
        expr = f"lower({expr})"
    return expr


# --------------------------------------------------------------------------
# File-name normalization / matching
# --------------------------------------------------------------------------

_FILE_DECODED = "decoded"
_FILE_EXACT = "exact"
_FILE_BOTH = "both"


def file_accepted_forms(value: str | None, cfg: Config) -> set[str]:
    """The set of accepted comparison forms for a file-name value."""
    if value is None:
        return set()
    raw = str(value).strip().strip("\"'")
    forms: set[str] = set()
    if cfg.file_match_strategy in (_FILE_EXACT, _FILE_BOTH):
        forms.add(raw)
    if cfg.file_match_strategy in (_FILE_DECODED, _FILE_BOTH):
        forms.add(unquote_plus(raw))
    if not cfg.file_match_case_sensitive:
        forms = {f.casefold() for f in forms}
    return forms


def file_names_match(db_name: str | None, target: str | None, cfg: Config) -> bool:
    """True when the DB file name overlaps with the target under the strategy."""
    left = file_accepted_forms(db_name, cfg)
    right = file_accepted_forms(target, cfg)
    return bool(left & right)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def csv_safe(value) -> str:
    if value is None:
        return ""
    return str(value)


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out