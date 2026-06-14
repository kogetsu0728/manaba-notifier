from __future__ import annotations

import logging
import os
import traceback
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from manaba_notifier.errors import NotifierError

LOG_DIRECTORY = Path.home() / ".local" / "state" / "manaba-notifier" / "logs"
PACKAGE_DIRECTORY = Path(__file__).resolve().parent
BACKUP_COUNT = 30

_LOG_FILES = {
    "deadline": "deadline-errors.log",
    "new-assignments": "new-assignments-errors.log",
}
_LOGGED_ATTRIBUTE = "_manaba_notifier_diagnostic_logged"


class _SecureTimedRotatingFileHandler(TimedRotatingFileHandler):
    def _open(self):  # type: ignore[no-untyped-def]
        fd = os.open(
            self.baseFilename,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o600,
        )
        os.chmod(self.baseFilename, 0o600)
        return open(
            fd,
            self.mode,
            encoding=self.encoding,
            errors=self.errors,
            closefd=True,
        )


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, NotifierError):
        return str(exc)
    return "予期しないエラーが発生した"


def _safe_traceback(exc: Exception) -> list[str]:
    frames: list[str] = []
    for frame, line_number in traceback.walk_tb(exc.__traceback__):
        path = Path(frame.f_code.co_filename).resolve()
        try:
            relative_path = path.relative_to(PACKAGE_DIRECTORY.parent)
        except ValueError:
            continue
        frames.append(
            f"  {relative_path}:{line_number} in {frame.f_code.co_name}"
        )
    return frames


def _format_entry(job: str, stage: str, exc: Exception) -> str:
    exception_type = f"{type(exc).__module__}.{type(exc).__qualname__}"
    lines = [
        f"timestamp={datetime.now(UTC).isoformat()}",
        f"job={job}",
        f"stage={stage}",
        f"exception={exception_type}",
        f"reason={_safe_reason(exc)}",
        "traceback:",
    ]
    frames = _safe_traceback(exc)
    lines.extend(frames or ["  (no application frames)"])
    return "\n".join(lines)


def record_failure(job: str, stage: str, exc: Exception) -> None:
    """Write a sanitized diagnostic entry without disrupting the job."""
    filename = _LOG_FILES.get(job)
    if filename is None:
        return

    handler: logging.Handler | None = None
    try:
        LOG_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(LOG_DIRECTORY, 0o700)
        handler = _SecureTimedRotatingFileHandler(
            LOG_DIRECTORY / filename,
            when="midnight",
            interval=1,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
            utc=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s\n"))
        record = logging.LogRecord(
            name="manaba_notifier.diagnostic",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg=_format_entry(job, stage, exc),
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        setattr(exc, _LOGGED_ATTRIBUTE, True)
    except Exception:
        pass
    finally:
        if handler is not None:
            handler.close()


def failure_was_recorded(exc: Exception) -> bool:
    return bool(getattr(exc, _LOGGED_ATTRIBUTE, False))
