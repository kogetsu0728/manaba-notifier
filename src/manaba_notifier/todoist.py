from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import requests

from manaba_notifier.error_details import request_detail
from manaba_notifier.errors import NotifierError
from manaba_notifier.models import Assignment

TODOIST_SYNC_URL = "https://api.todoist.com/api/v1/sync"
MAX_COMMANDS = 100
RETRY_DELAYS = (1.0, 3.0)


class TodoistError(RuntimeError, NotifierError):
    """Raised when Todoist synchronization fails."""


@dataclass(frozen=True)
class TodoistCommand:
    uuid: str
    type: str
    args: Mapping[str, object]
    temp_id: str | None = None

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "uuid": self.uuid,
            "type": self.type,
            "args": dict(self.args),
        }
        if self.temp_id:
            payload["temp_id"] = self.temp_id
        return payload


@dataclass(frozen=True)
class TodoistSyncResult:
    succeeded: set[str]
    failed: set[str]
    task_ids: dict[str, str]


def task_fields(
    assignment: Assignment,
    project_id: str,
    timezone: str,
) -> dict[str, object]:
    description_lines = [
        f"種類: {assignment.type or '不明'}",
        f"受付開始: {assignment.start_at.isoformat() if assignment.start_at else 'なし'}",
    ]
    if assignment.url:
        description_lines.append(f"manaba: {assignment.url}")

    fields: dict[str, object] = {
        "content": f"[{assignment.course or '科目不明'}] {assignment.title}",
        "description": "\n".join(description_lines),
        "project_id": project_id,
        "due": None,
    }
    if assignment.end_at is not None:
        due_utc = assignment.end_at.astimezone(UTC)
        fields["due"] = {
            "date": due_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timezone": timezone,
        }
    return fields


def sync_commands(token: str, commands: Sequence[TodoistCommand]) -> TodoistSyncResult:
    if not commands:
        return TodoistSyncResult(set(), set(), {})
    if len(commands) > MAX_COMMANDS:
        raise ValueError(f"Todoist Sync APIは1回{MAX_COMMANDS}コマンドまで")

    attempts = len(RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            response = requests.post(
                TODOIST_SYNC_URL,
                headers={"Authorization": f"Bearer {token}"},
                data={"commands": _commands_json(commands)},
                timeout=30,
            )
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt < len(RETRY_DELAYS) and _should_retry(exc):
                time.sleep(RETRY_DELAYS[attempt])
                continue
            raise TodoistError(_request_error_message(exc, attempt + 1)) from exc
    else:
        raise TodoistError("Todoist APIへの接続に失敗した")

    try:
        data: Any = response.json()
    except ValueError as exc:
        raise TodoistError("Todoist APIから不正な応答を受信した") from exc

    if not isinstance(data, dict) or not isinstance(data.get("sync_status"), dict):
        raise TodoistError("Todoist APIから不正な応答を受信した")

    statuses = data["sync_status"]
    succeeded = {
        command.uuid for command in commands if statuses.get(command.uuid) == "ok"
    }
    failed = {command.uuid for command in commands if command.uuid not in succeeded}
    raw_mapping = data.get("temp_id_mapping", {})
    task_ids = (
        {
            key: value
            for key, value in raw_mapping.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(raw_mapping, dict)
        else {}
    )
    return TodoistSyncResult(succeeded, failed, task_ids)


def _commands_json(commands: Sequence[TodoistCommand]) -> str:
    import json

    return json.dumps([command.payload() for command in commands], ensure_ascii=False)


def _should_retry(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    if response is None:
        return True
    return response.status_code == 429 or 500 <= response.status_code < 600


def _request_error_message(exc: requests.RequestException, attempts: int) -> str:
    detail = request_detail(exc)
    return f"Todoist APIへの接続に失敗した ({detail}; {attempts}回試行)"
