"""Logging setup: human friendly console logs plus a per-run log file."""

import logging
import sys
from pathlib import Path

from config import Config

_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"


def setup_logging(cfg: Config, log_dir: Path | None = None) -> logging.Logger:
    level = getattr(logging, cfg.log_level, logging.INFO)

    root = logging.getLogger("nps_drop")
    root.setLevel(level)
    root.handlers.clear()
    root.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(file_handler)
        root.info("Logging to %s", log_dir / "run.log")

    return root


class SectionLog:
    """Small helper to print clearly delimited pipeline sections."""

    def __init__(self, logger: logging.Logger):
        self._log = logger
        self._step = 0

    def step(self, title: str, detail: str = "") -> None:
        self._step += 1
        bar = "=" * 70
        self._log.info("")
        self._log.info(bar)
        self._log.info("STEP %d  -  %s", self._step, title)
        if detail:
            self._log.info("           %s", detail)
        self._log.info(bar)