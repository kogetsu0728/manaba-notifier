from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from manaba_notifier.errors import NotifierError


class ConfigError(ValueError, NotifierError):
    """Raised when application configuration is invalid."""


class ManabaConfig(Protocol):
    manaba_login_url: str
    manaba_assignments_url: str
    manaba_id: str
    manaba_password: str
    timezone: str
    chrome_path: str | None


@dataclass(frozen=True)
class Config:
    manaba_login_url: str
    manaba_assignments_url: str
    manaba_id: str = field(repr=False)
    manaba_password: str = field(repr=False)
    deadline_assignments_discord_webhook_url: str = field(repr=False)
    notify_within_days: int = 3
    notify_empty: bool = True
    timezone: str = "Asia/Tokyo"
    chrome_path: str | None = None


@dataclass(frozen=True)
class NewAssignmentsConfig:
    manaba_login_url: str
    manaba_assignments_url: str
    manaba_id: str = field(repr=False)
    manaba_password: str = field(repr=False)
    new_assignments_discord_webhook_url: str = field(repr=False)
    todoist_api_token: str = field(repr=False)
    todoist_project_id: str
    timezone: str = "Asia/Tokyo"
    chrome_path: str | None = None


@dataclass(frozen=True)
class _CommonConfig:
    manaba_login_url: str
    manaba_assignments_url: str
    manaba_id: str = field(repr=False)
    manaba_password: str = field(repr=False)
    timezone: str = "Asia/Tokyo"
    chrome_path: str | None = None


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"必須環境変数 {name} が設定されていない")
    return value


def _parse_non_negative_int(name: str, default: str) -> int:
    raw_value = os.getenv(name, default).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"環境変数 {name} は整数で指定する必要がある") from exc
    if value < 0:
        raise ConfigError(f"環境変数 {name} は0以上で指定する必要がある")
    return value


def _parse_bool(name: str, default: str) -> bool:
    raw_value = os.getenv(name, default).strip().lower()
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    raise ConfigError(f"環境変数 {name} は true または false で指定する必要がある")


def _load_common() -> _CommonConfig:
    timezone = os.getenv("TIMEZONE", "Asia/Tokyo").strip()
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError("環境変数 TIMEZONE に有効なタイムゾーンを指定する必要がある") from exc

    chrome_path = os.getenv("CHROME_PATH", "").strip() or None

    return _CommonConfig(
        manaba_login_url=_required("MANABA_LOGIN_URL"),
        manaba_assignments_url=_required("MANABA_ASSIGNMENTS_URL"),
        manaba_id=_required("MANABA_ID"),
        manaba_password=_required("MANABA_PASSWORD"),
        timezone=timezone,
        chrome_path=chrome_path,
    )


def load_config() -> Config:
    load_dotenv()
    common = _load_common()

    return Config(
        manaba_login_url=common.manaba_login_url,
        manaba_assignments_url=common.manaba_assignments_url,
        manaba_id=common.manaba_id,
        manaba_password=common.manaba_password,
        timezone=common.timezone,
        chrome_path=common.chrome_path,
        deadline_assignments_discord_webhook_url=_required(
            "DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL"
        ),
        notify_within_days=_parse_non_negative_int("NOTIFY_WITHIN_DAYS", "3"),
        notify_empty=_parse_bool("NOTIFY_EMPTY", "true"),
    )


def load_new_assignments_config() -> NewAssignmentsConfig:
    load_dotenv()
    common = _load_common()

    return NewAssignmentsConfig(
        manaba_login_url=common.manaba_login_url,
        manaba_assignments_url=common.manaba_assignments_url,
        manaba_id=common.manaba_id,
        manaba_password=common.manaba_password,
        timezone=common.timezone,
        chrome_path=common.chrome_path,
        new_assignments_discord_webhook_url=_required(
            "NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL"
        ),
        todoist_api_token=_required("TODOIST_API_TOKEN"),
        todoist_project_id=_required("TODOIST_PROJECT_ID"),
    )
