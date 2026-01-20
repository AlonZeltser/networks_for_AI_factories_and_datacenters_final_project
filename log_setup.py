"""Centralized logging setup helper used by small runners/tests.

Place small, safe logging initialization here so scripts can call it before importing
other modules that may configure logging (matplotlib, third-party libs, etc.).

Logging behavior:
- Console: INFO (by default)
- File: DEBUG (per-run logfile)

The per-run logfile name includes the run tag (e.g., topology+scenario), but the log
line format itself does NOT include topology/scenario.
"""

import datetime
import logging
import os
import sys
import secrets

DEFAULT_FORMAT = "%(asctime)s [%(levelname)-7s] %(filename)s:%(lineno)d %(message)s"
DEFAULT_DATEFMT = "%H:%M:%S"


def ensure_logging(level: int = logging.INFO, *, force: bool = False) -> None:
    """Ensure the root logger is configured with a StreamHandler to stdout."""
    root = logging.getLogger()
    if force or not root.handlers:
        logging.basicConfig(level=level, format=DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT, stream=sys.stdout, force=force)
    else:
        root.setLevel(level)


def configure_debug(debug: bool) -> None:
    """Convenience wrapper to set DEBUG level when requested."""
    ensure_logging(logging.DEBUG if debug else logging.INFO)


def configure_run_logging(
    run_tag: str,
    *,
    log_dir: str = "results/logs",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    force: bool = True,
) -> str:
    """Configure per-run logging.

    - Console handler at `console_level`.
    - File handler at `file_level`.
    - Returns absolute logfile path.

    `run_tag` is used ONLY in the logfile filename (not in log lines).
    """

    # Start from a clean slate so repeated runs don't duplicate handlers.
    ensure_logging(level=console_level, force=force)
    root = logging.getLogger()

    # Quiet noisy third-party loggers
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Use microseconds + a short random suffix so consecutive runs don't collide.
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = secrets.token_hex(2)
    safe_tag = "".join(c if c.isalnum() or c in "._-" else "_" for c in (run_tag or "run"))
    logfile = os.path.abspath(os.path.join(log_dir, f"{safe_tag}_{ts}_{suffix}.log"))

    # Replace the basicConfig-created handlers with our aligned formatter + levels
    fmt = logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT)

    # Remove any existing handlers (basicConfig added one StreamHandler).
    for h in list(root.handlers):
        root.removeHandler(h)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = logging.FileHandler(logfile, mode="a", encoding="utf-8")
    fh.setLevel(file_level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Root must be low enough so file gets DEBUG.
    root.setLevel(min(console_level, file_level))

    return logfile
