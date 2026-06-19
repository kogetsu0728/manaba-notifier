from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from manaba_notifier.models import Assignment
from manaba_notifier.new_assignments_state import (
    NewAssignmentsState,
    StateError,
    TodoistTaskState,
    assignment_fingerprint,
    assignment_id,
    current_assignment_ids,
    find_new_assignments,
    load_state,
    save_state,
)


def _assignment(title: str, url: str | None = None) -> Assignment:
    return Assignment(
        type="レポート",
        title=title,
        course="科目",
        start_at=datetime(2026, 6, 1, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        end_at=datetime(2026, 6, 30, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        url=url,
    )


def test_assignment_identifiers_and_fingerprints_are_stable() -> None:
    assignment = _assignment("課題", "https://manaba.example/a")
    assert assignment_id(assignment) == "url:https://manaba.example/a"
    assert assignment_fingerprint(assignment) == assignment_fingerprint(assignment)


def test_find_new_assignments_handles_initial_add_remove_and_reappearance() -> None:
    first = _assignment("課題1", "https://manaba.example/1")
    second = _assignment("課題2", "https://manaba.example/2")
    assert find_new_assignments([first, second], None) == [first, second]
    assert find_new_assignments([first, second], current_assignment_ids([first])) == [
        second
    ]
    assert find_new_assignments([first, second], current_assignment_ids([second])) == [
        first
    ]


def test_save_and_load_state_with_private_permissions(tmp_path: Path) -> None:
    path = tmp_path / "state" / "new-assignments.json"
    state = NewAssignmentsState(
        assignment_ids={"url:https://manaba.example/1"},
        todoist_tasks={
            "url:https://manaba.example/1": TodoistTaskState(
                task_id="task-id",
                fingerprint="fingerprint",
                create_command_uuid="command-id",
                temp_id="temp-id",
            )
        },
    )
    save_state(path, state)

    assert load_state(path) == state
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2


def test_load_state_migrates_version_1_without_renotifying(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"version": 1, "assignment_ids": ["url:one"]}),
        encoding="utf-8",
    )

    assert load_state(path) == NewAssignmentsState(assignment_ids={"url:one"})


def test_load_state_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_state(tmp_path / "missing.json") == NewAssignmentsState()


@pytest.mark.parametrize(
    "content",
    ["not json", '{"version": 99, "assignment_ids": []}', '{"version": 2}'],
)
def test_load_state_rejects_corrupt_state(tmp_path: Path, content: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StateError):
        load_state(path)


def test_load_state_reports_read_failure_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")

    def fail_read(*args: object, **kwargs: object) -> str:
        raise OSError("secret read detail")

    monkeypatch.setattr(Path, "read_text", fail_read)

    with pytest.raises(StateError) as exc_info:
        load_state(path)

    assert "OSError" in str(exc_info.value)
    assert "secret read detail" not in str(exc_info.value)


def test_save_state_keeps_previous_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("previous", encoding="utf-8")

    def fail_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("manaba_notifier.new_assignments_state.os.replace", fail_replace)
    with pytest.raises(StateError, match="保存できない") as exc_info:
        save_state(path, NewAssignmentsState())
    assert "OSError" in str(exc_info.value)
    assert "replace failed" not in str(exc_info.value)
    assert path.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".state.json.*")) == []
