from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from manaba_notifier.collector import collect_assignments
from manaba_notifier.config import Config, load_config
from manaba_notifier.discord import (
    build_assignment_payload,
    post_webhook,
)
from manaba_notifier.filter import filter_assignments
from manaba_notifier.runtime import run_job


def _execute(config: Config) -> None:
    assignments = collect_assignments(config)
    now = datetime.now(ZoneInfo(config.timezone))
    selected = filter_assignments(assignments, now, config.notify_within_days)

    if selected or config.notify_empty:
        payload = build_assignment_payload(
            selected,
            config.notify_within_days,
            now,
        )
        post_webhook(config.deadline_assignments_discord_webhook_url, payload)


def run() -> int:
    return run_job(
        load_config=load_config,
        execute=_execute,
        webhook_url=lambda config: config.deadline_assignments_discord_webhook_url,
        fallback_webhook_env="DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL",
        failure_label="manaba課題通知に失敗した",
        job_name="deadline",
    )


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
