from __future__ import annotations

import pytest

from manaba_notifier.config import (
    Config,
    ConfigError,
    load_config,
    load_new_assignments_config,
)


REQUIRED_ENV = {
    "MANABA_LOGIN_URL": "https://manaba.example/login",
    "MANABA_ASSIGNMENTS_URL": "https://manaba.example/assignments",
    "MANABA_ID": "student-id",
    "MANABA_PASSWORD": "secret-password",
    "DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL": "https://discord.example/webhook-secret",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        *REQUIRED_ENV,
        "DISCORD_WEBHOOK_URL",
        "NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL",
        "TODOIST_API_TOKEN",
        "TODOIST_PROJECT_ID",
        "NOTIFY_WITHIN_DAYS",
        "NOTIFY_EMPTY",
        "TIMEZONE",
        "CHROME_PATH",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("manaba_notifier.config.load_dotenv", lambda: False)


def _set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)


def test_load_config_uses_defaults_and_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)

    config = load_config()

    assert config.notify_within_days == 3
    assert config.notify_empty is True
    assert config.timezone == "Asia/Tokyo"
    assert config.chrome_path is None
    assert "secret-password" not in repr(config)
    assert "webhook-secret" not in repr(config)


def test_config_keeps_original_positional_constructor() -> None:
    config = Config(
        "https://manaba.example/login",
        "https://manaba.example/assignments",
        "student-id",
        "secret-password",
        "https://discord.example/webhook",
    )

    assert config.notify_within_days == 3
    assert config.notify_empty is True


def test_load_config_requires_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    monkeypatch.delenv("MANABA_ID")

    with pytest.raises(ConfigError, match="MANABA_ID"):
        load_config()


def test_existing_config_does_not_require_new_assignments_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required(monkeypatch)

    assert load_config().deadline_assignments_discord_webhook_url == REQUIRED_ENV[
        "DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL"
    ]


def test_load_new_assignments_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    monkeypatch.delenv("DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL")
    monkeypatch.setenv(
        "NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL",
        "https://discord.example/new-assignments-secret",
    )
    monkeypatch.setenv("TODOIST_API_TOKEN", "todoist-secret")
    monkeypatch.setenv("TODOIST_PROJECT_ID", "project-id")

    config = load_new_assignments_config()

    assert config.timezone == "Asia/Tokyo"
    assert "new-assignments-secret" not in repr(config)
    assert "todoist-secret" not in repr(config)
    assert config.todoist_project_id == "project-id"


def test_load_config_does_not_accept_legacy_webhook_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required(monkeypatch)
    monkeypatch.delenv("DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL")
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL",
        "https://discord.example/legacy-webhook-secret",
    )

    with pytest.raises(ConfigError, match="DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL"):
        load_config()


def test_load_new_assignments_config_requires_own_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required(monkeypatch)

    with pytest.raises(ConfigError, match="NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL"):
        load_new_assignments_config()


@pytest.mark.parametrize("name", ["TODOIST_API_TOKEN", "TODOIST_PROJECT_ID"])
def test_load_new_assignments_config_requires_todoist_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv(
        "NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL",
        "https://discord.example/new-assignments-secret",
    )
    monkeypatch.setenv("TODOIST_API_TOKEN", "todoist-secret")
    monkeypatch.setenv("TODOIST_PROJECT_ID", "project-id")
    monkeypatch.delenv(name)

    with pytest.raises(ConfigError, match=name):
        load_new_assignments_config()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("NOTIFY_WITHIN_DAYS", "abc", "整数"),
        ("NOTIFY_WITHIN_DAYS", "-1", "0以上"),
        ("NOTIFY_EMPTY", "yes", "true または false"),
        ("TIMEZONE", "Invalid/Timezone", "有効なタイムゾーン"),
    ],
)
def test_load_config_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError, match=message):
        load_config()
