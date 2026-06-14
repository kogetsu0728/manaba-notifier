from __future__ import annotations

from typing import Any

from manaba_notifier.config import Config
from manaba_notifier.main import run


def _config(notify_empty: bool) -> Config:
    return Config(
        manaba_login_url="https://manaba.example/login",
        manaba_assignments_url="https://manaba.example/assignments",
        manaba_id="id",
        manaba_password="password",
        deadline_assignments_discord_webhook_url=(
            "https://discord.example/webhook"
        ),
        notify_within_days=3,
        notify_empty=notify_empty,
        timezone="Asia/Tokyo",
    )


def test_run_skips_empty_notification_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr("manaba_notifier.main.load_config", lambda: _config(False))
    monkeypatch.setattr("manaba_notifier.main.collect_assignments", lambda config: [])
    posts: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "manaba_notifier.main.post_webhook",
        lambda url, payload: posts.append((url, payload)),
    )

    assert run() == 0
    assert posts == []


def test_run_posts_empty_notification_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr("manaba_notifier.main.load_config", lambda: _config(True))
    monkeypatch.setattr("manaba_notifier.main.collect_assignments", lambda config: [])
    posts: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "manaba_notifier.main.post_webhook",
        lambda url, payload: posts.append((url, payload)),
    )

    assert run() == 0
    assert posts[0][0] == "https://discord.example/webhook"
    assert posts[0][1]["embeds"][0]["title"] == "manaba 未提出課題"
    assert posts[0][1]["embeds"][0]["color"] == 0x57F287
