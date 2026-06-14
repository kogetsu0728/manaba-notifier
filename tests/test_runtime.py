from __future__ import annotations

from dataclasses import dataclass

from manaba_notifier.discord import DiscordError
from manaba_notifier.errors import NotifierError
from manaba_notifier.runtime import notify_failure, run_job, safe_reason


class ExpectedError(NotifierError):
    pass


@dataclass(frozen=True)
class DummyConfig:
    webhook_url: str


def test_safe_reason_preserves_only_notifier_errors() -> None:
    assert safe_reason(ExpectedError("安全な原因")) == "安全な原因"
    assert safe_reason(RuntimeError("秘密を含む可能性")) == "予期しないエラーが発生した"


def test_run_job_executes_loaded_config() -> None:
    config = DummyConfig("https://discord.example/webhook")
    executed: list[DummyConfig] = []

    result = run_job(
        load_config=lambda: config,
        execute=executed.append,
        webhook_url=lambda loaded: loaded.webhook_url,
        fallback_webhook_env="TEST_WEBHOOK_URL",
        failure_label="テスト失敗",
        job_name="deadline",
    )

    assert result == 0
    assert executed == [config]


def test_run_job_reports_sanitized_unexpected_error(
    monkeypatch,
    capsys,
) -> None:
    config = DummyConfig("https://discord.example/webhook")
    reported: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "manaba_notifier.runtime.notify_failure",
        lambda url, reason: reported.append((url, reason)),
    )
    monkeypatch.setattr(
        "manaba_notifier.runtime.record_failure",
        lambda job, stage, exc: None,
    )

    def fail(_: DummyConfig) -> None:
        raise RuntimeError("秘密を含む可能性")

    result = run_job(
        load_config=lambda: config,
        execute=fail,
        webhook_url=lambda loaded: loaded.webhook_url,
        fallback_webhook_env="TEST_WEBHOOK_URL",
        failure_label="テスト失敗",
        job_name="deadline",
    )

    assert result == 1
    assert reported == [
        ("https://discord.example/webhook", "予期しないエラーが発生した")
    ]
    assert capsys.readouterr().err == (
        "テスト失敗。原因: 予期しないエラーが発生した\n"
    )


def test_run_job_uses_fallback_webhook_when_config_load_fails(
    monkeypatch,
) -> None:
    reported: list[tuple[str, str]] = []
    monkeypatch.setenv("TEST_WEBHOOK_URL", "https://discord.example/fallback")
    monkeypatch.setattr(
        "manaba_notifier.runtime.notify_failure",
        lambda url, reason: reported.append((url, reason)),
    )
    monkeypatch.setattr(
        "manaba_notifier.runtime.record_failure",
        lambda job, stage, exc: None,
    )

    def fail_load() -> DummyConfig:
        raise ExpectedError("設定エラー")

    result = run_job(
        load_config=fail_load,
        execute=lambda config: None,
        webhook_url=lambda config: config.webhook_url,
        fallback_webhook_env="TEST_WEBHOOK_URL",
        failure_label="テスト失敗",
        job_name="deadline",
    )

    assert result == 1
    assert reported == [("https://discord.example/fallback", "設定エラー")]


def test_notify_failure_suppresses_discord_failure(monkeypatch) -> None:
    def fail_post(url: str, payload: dict[str, object]) -> None:
        raise DiscordError("Discord Webhookへの投稿に失敗した")

    monkeypatch.setattr("manaba_notifier.runtime.post_webhook", fail_post)

    notify_failure("https://discord.example/webhook", "原因")
