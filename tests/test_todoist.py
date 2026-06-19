from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from manaba_notifier.models import Assignment
from manaba_notifier.todoist import (
    TodoistCommand,
    TodoistError,
    sync_commands,
    task_fields,
)


def test_task_fields_include_metadata_and_fixed_due_date() -> None:
    assignment = Assignment(
        "レポート",
        "課題",
        "科目",
        datetime(2026, 6, 1, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        datetime(2026, 6, 30, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        "https://manaba.example/1",
    )

    fields = task_fields(assignment, "project-id", "Asia/Tokyo")

    assert fields["content"] == "[科目] 課題"
    assert fields["project_id"] == "project-id"
    assert fields["due"] == {
        "date": "2026-06-30T14:00:00Z",
        "timezone": "Asia/Tokyo",
    }
    assert "https://manaba.example/1" in fields["description"]


def test_task_fields_allow_missing_due_date() -> None:
    assignment = Assignment("小テスト", "課題", "科目", None, None, None)
    assert task_fields(assignment, "project-id", "Asia/Tokyo")["due"] is None


def test_sync_commands_parses_success_and_mapping(monkeypatch) -> None:
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "sync_status": {"command-id": "ok"},
                "temp_id_mapping": {"temp-id": "task-id"},
            },
        },
    )()
    captured: dict[str, object] = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr("manaba_notifier.todoist.requests.post", post)
    command = TodoistCommand("command-id", "item_add", {"content": "課題"}, "temp-id")

    result = sync_commands("secret-token", [command])

    assert result.succeeded == {"command-id"}
    assert result.task_ids == {"temp-id": "task-id"}
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}


def test_sync_commands_hides_token_on_failure(monkeypatch) -> None:
    monkeypatch.setattr("manaba_notifier.todoist.time.sleep", lambda delay: None)

    def fail(*args, **kwargs):
        raise requests.RequestException("secret-token")

    monkeypatch.setattr("manaba_notifier.todoist.requests.post", fail)
    with pytest.raises(TodoistError) as exc_info:
        sync_commands(
            "secret-token",
            [TodoistCommand("command-id", "item_close", {"id": "task-id"})],
        )
    assert "secret-token" not in str(exc_info.value)
    assert "RequestException" in str(exc_info.value)
    assert "3回試行" in str(exc_info.value)


def test_sync_commands_retries_transient_failure(monkeypatch) -> None:
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"sync_status": {"command-id": "ok"}},
        },
    )()
    calls = 0

    def post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.Timeout("temporary")
        return response

    monkeypatch.setattr("manaba_notifier.todoist.time.sleep", lambda delay: None)
    monkeypatch.setattr("manaba_notifier.todoist.requests.post", post)

    result = sync_commands(
        "secret-token",
        [TodoistCommand("command-id", "item_close", {"id": "task-id"})],
    )

    assert result.succeeded == {"command-id"}
    assert calls == 2


def test_sync_commands_reports_http_status_without_body(monkeypatch) -> None:
    class Response:
        status_code = 500
        text = "server detail"

        def raise_for_status(self):
            raise requests.HTTPError("server detail", response=self)

    monkeypatch.setattr("manaba_notifier.todoist.time.sleep", lambda delay: None)
    monkeypatch.setattr(
        "manaba_notifier.todoist.requests.post", lambda *args, **kwargs: Response()
    )

    with pytest.raises(TodoistError) as exc_info:
        sync_commands(
            "secret-token",
            [TodoistCommand("command-id", "item_close", {"id": "task-id"})],
        )

    assert "HTTP 500" in str(exc_info.value)
    assert "server detail" not in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
