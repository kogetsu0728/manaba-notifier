from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import TypeVar

from manaba_notifier.diagnostic_log import failure_was_recorded, record_failure
from manaba_notifier.discord import DiscordError, build_error_payload, post_webhook
from manaba_notifier.errors import NotifierError

ConfigT = TypeVar("ConfigT")


def safe_reason(exc: Exception) -> str:
    if isinstance(exc, NotifierError):
        return str(exc)
    return "予期しないエラーが発生した"


def notify_failure(webhook_url: str, reason: str) -> None:
    if not webhook_url:
        return
    try:
        post_webhook(webhook_url, build_error_payload(reason))
    except DiscordError:
        pass


def run_job(
    *,
    load_config: Callable[[], ConfigT],
    execute: Callable[[ConfigT], None],
    webhook_url: Callable[[ConfigT], str],
    fallback_webhook_env: str,
    failure_label: str,
    job_name: str,
) -> int:
    config: ConfigT | None = None
    try:
        try:
            config = load_config()
        except Exception as exc:
            record_failure(job_name, "config", exc)
            raise

        try:
            execute(config)
        except Exception as exc:
            if not failure_was_recorded(exc):
                record_failure(job_name, "execute", exc)
            raise
        return 0
    except Exception as exc:
        reason = safe_reason(exc)
        error_webhook_url = (
            webhook_url(config)
            if config is not None
            else os.getenv(fallback_webhook_env, "").strip()
        )
        notify_failure(error_webhook_url, reason)
        print(f"{failure_label}。原因: {reason}", file=sys.stderr)
        return 1
