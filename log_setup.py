"""Centralized logging setup helper used by small runners/tests.

Place small, safe logging initialization here so scripts can call it before importing
other modules that may configure logging (matplotlib, third-party libs, etc.).
"""
import logging
import sys
import os
import datetime

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s"
DEFAULT_DATEFMT = "%H:%M:%S"


def ensure_logging(level: int = logging.INFO, *, force: bool = False) -> None:
    """Ensure the root logger is configured with a StreamHandler to stdout.

    - If the root logger has no handlers, configure one via basicConfig.
    - If handlers exist and `force` is True, reconfigure (Python 3.8+).
    - Otherwise, set the root logger level to `level` without replacing handlers.

    This is safe to call multiple times.
    """
    root = logging.getLogger()
    if force or not root.handlers:
        # basicConfig with force will replace existing handlers (3.8+)
        logging.basicConfig(level=level, format=DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT, stream=sys.stdout, force=force)
    else:
        root.setLevel(level)


def configure_debug(debug: bool) -> None:
    """Convenience wrapper to set DEBUG level when requested."""
    ensure_logging(logging.DEBUG if debug else logging.INFO)


# --- New: per-run logging configuration ---

def configure_run_logging(topology: str, scenario: str, *, log_dir: str = "results/logs",
                          console_level: int = logging.INFO, file_level: int = logging.DEBUG,
                          force: bool = False) -> str:
    """Configure logging for a run.

    - Ensures a console StreamHandler exists (INFO by default).
    - Adds a per-run file handler at DEBUG level that captures all messages.
    - Does NOT include topology/scenario in each log line (only the logfile name).
    - Returns the absolute path to the logfile created.

    If `force` is True the root handlers will be replaced.
    """
    ensure_logging(level=console_level, force=force)

    # Quiet noisy third-party loggers early so they don't flood logs at DEBUG
    try:
        logging.getLogger("matplotlib").setLevel(logging.WARNING)
        logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    except Exception:
        pass

    # Build logfile name (includes topology+scenario), but do not include them in each log line.
    topo = (topology or "unknown").lower()
    scen = (scenario or "none").lower()
    file_tag = f"{topo}.{scen}"

    # Create log directory
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_tag = "".join(c if c.isalnum() or c in '._-' else '_' for c in file_tag)
    logfile = os.path.join(log_dir, f"{safe_tag}_{timestamp}.log")

    root = logging.getLogger()

    # If not forcing, avoid adding multiple file handlers for the same logfile/run
    existing_files = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    if not force:
        for h in existing_files:
            # If a FileHandler already writes to our logfile (or any file including run name), reuse
            try:
                if hasattr(h, 'baseFilename') and safe_tag in os.path.basename(h.baseFilename):
                    return os.path.abspath(h.baseFilename)
            except Exception:
                continue

    # Create formatter with aligned fields. Keep a fixed width level column so messages align.
    # Example: "17:22:40 [INFO   ] network.py:65 Scenario created."
    fmt = "%(asctime)s [%(levelname)-7s] %(filename)s:%(lineno)d %(message)s"
    datefmt = DEFAULT_DATEFMT

    # No per-run label injected into log lines.
    run_filter = None

    # Console handler: ensure there's a StreamHandler writing to stdout at console_level
    console_exists = any(isinstance(h, logging.StreamHandler) and (getattr(h, 'stream', None) in (sys.stdout, None)) for h in root.handlers)
    if not console_exists or force:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        if run_filter is not None:
            ch.addFilter(run_filter)
        # If force, remove existing stream handlers to avoid duplicates
        if force:
            root.handlers = [h for h in root.handlers if not isinstance(h, logging.StreamHandler)]
        root.addHandler(ch)

    # File handler: always add a file handler for this run (unless a matching one exists and not forcing)
    fh = logging.FileHandler(logfile, mode='a', encoding='utf-8')
    fh.setLevel(file_level)
    fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    if run_filter is not None:
        fh.addFilter(run_filter)
    root.addHandler(fh)

    # Keep root level at the lower of console/file so file captures debug
    root.setLevel(min(console_level, file_level))

    return os.path.abspath(logfile)
