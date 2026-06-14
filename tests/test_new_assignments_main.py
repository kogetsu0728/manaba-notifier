from __future__ import annotations

from typing import Any

import pytest

from manaba_notifier.config import NewAssignmentsConfig
from manaba_notifier.discord import DiscordError
from manaba_notifier.models import Assignment
from manaba_notifier.new_assignments_main import (
    _apply_success,
    _execute,
    _todoist_operations,
)
from manaba_notifier.new_assignments_state import (
    NewAssignmentsState,
    TodoistTaskState,
    assignment_fingerprint,
    assignment_id,
)


@pytest.fixture(autouse=True)
def _disable_diagnostic_log(monkeypatch) -> None:
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.record_failure",
        lambda job, stage, exc: None,
    )


def _config() -> NewAssignmentsConfig:
    return NewAssignmentsConfig(
        manaba_login_url="https://manaba.example/login",
        manaba_assignments_url="https://manaba.example/assignments",
        manaba_id="id",
        manaba_password="password",
        new_assignments_discord_webhook_url="https://discord.example/new",
        todoist_api_token="todoist-secret",
        todoist_project_id="project-id",
    )


def _assignment(title: str, url: str) -> Assignment:
    return Assignment("レポート", title, "科目", None, None, url)


def test_operations_create_update_close_and_uncomplete() -> None:
    current = _assignment("現在", "https://manaba.example/current")
    changed = _assignment("変更後", "https://manaba.example/changed")
    reopened = _assignment("再出現", "https://manaba.example/reopened")
    removed = _assignment("消失", "https://manaba.example/removed")
    state = NewAssignmentsState(
        todoist_tasks={
            assignment_id(changed): TodoistTaskState("changed-id", "old"),
            assignment_id(reopened): TodoistTaskState(
                "reopened-id", assignment_fingerprint(reopened), True
            ),
            assignment_id(removed): TodoistTaskState(
                "removed-id", assignment_fingerprint(removed)
            ),
        }
    )

    operations = _todoist_operations([current, changed, reopened], state, _config())

    assert [operation.action for operation in operations] == [
        "create",
        "update",
        "uncomplete",
        "close",
    ]
    assert [operation.command.type for operation in operations] == [
        "item_add",
        "item_update",
        "item_uncomplete",
        "item_close",
    ]


def test_transition_uuid_is_reused_for_retry_but_not_next_cycle() -> None:
    assignment = _assignment("課題", "https://manaba.example/1")
    identifier = assignment_id(assignment)
    state = NewAssignmentsState(
        todoist_tasks={
            identifier: TodoistTaskState(
                "task-id", assignment_fingerprint(assignment)
            )
        }
    )

    first_close = _todoist_operations([], state, _config())[0]
    retry_close = _todoist_operations([], state, _config())[0]
    assert retry_close.command.uuid == first_close.command.uuid
    assert _apply_success(first_close, {}, state)

    uncomplete = _todoist_operations([assignment], state, _config())[0]
    assert _apply_success(uncomplete, {}, state)
    second_close = _todoist_operations([], state, _config())[0]

    assert second_close.command.uuid != first_close.command.uuid


def test_execute_saves_discord_success_when_todoist_fails(monkeypatch) -> None:
    assignment = _assignment("課題", "https://manaba.example/1")
    state = NewAssignmentsState()
    saved: list[NewAssignmentsState] = []
    posts: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.collect_assignments",
        lambda config: [assignment],
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.load_state", lambda path: state
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.save_state",
        lambda path, current: saved.append(
            NewAssignmentsState(set(current.assignment_ids), dict(current.todoist_tasks))
        ),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.post_webhook",
        lambda url, payload: posts.append(payload),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.sync_commands",
        lambda token, commands: (_ for _ in ()).throw(RuntimeError("todoist failed")),
    )

    try:
        _execute(_config())
    except RuntimeError:
        pass

    assert len(posts) == 1
    assert saved[0].assignment_ids == {assignment_id(assignment)}


def test_execute_attempts_todoist_when_discord_fails(monkeypatch) -> None:
    assignment = _assignment("課題", "https://manaba.example/1")
    synced: list[object] = []
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.collect_assignments",
        lambda config: [assignment],
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.load_state",
        lambda path: NewAssignmentsState(),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.save_state", lambda path, state: None
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.post_webhook",
        lambda url, payload: (_ for _ in ()).throw(DiscordError("discord failed")),
    )

    def sync(token, commands):
        synced.extend(commands)
        from manaba_notifier.todoist import TodoistSyncResult

        command = commands[0]
        return TodoistSyncResult(
            {command.uuid}, set(), {command.temp_id: "todoist-task-id"}
        )

    monkeypatch.setattr("manaba_notifier.new_assignments_main.sync_commands", sync)

    try:
        _execute(_config())
    except DiscordError:
        pass

    assert len(synced) == 1


def test_execute_records_discord_and_todoist_failures(monkeypatch) -> None:
    recorded: list[tuple[str, str, Exception]] = []
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.collect_assignments",
        lambda config: [],
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.load_state",
        lambda path: NewAssignmentsState(),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main._notify_discord",
        lambda assignments, state, config: (_ for _ in ()).throw(
            RuntimeError("discord detail")
        ),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main._sync_todoist",
        lambda assignments, state, config: (_ for _ in ()).throw(
            RuntimeError("todoist detail")
        ),
    )
    monkeypatch.setattr(
        "manaba_notifier.new_assignments_main.record_failure",
        lambda job, stage, exc: recorded.append((job, stage, exc)),
    )

    with pytest.raises(RuntimeError, match="discord detail"):
        _execute(_config())

    assert [(job, stage) for job, stage, _ in recorded] == [
        ("new-assignments", "discord"),
        ("new-assignments", "todoist"),
    ]
