from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from manaba_notifier.error_details import exception_type, with_detail
from manaba_notifier.errors import NotifierError
from manaba_notifier.models import Assignment

STATE_VERSION = 2


class StateError(RuntimeError, NotifierError):
    """Raised when the new-assignment snapshot cannot be read or written."""


@dataclass
class TodoistTaskState:
    task_id: str | None = None
    fingerprint: str = ""
    completed: bool = False
    create_command_uuid: str = ""
    temp_id: str = ""
    pending_commands: dict[str, str] = field(default_factory=dict)


@dataclass
class NewAssignmentsState:
    assignment_ids: set[str] = field(default_factory=set)
    todoist_tasks: dict[str, TodoistTaskState] = field(default_factory=dict)


def assignment_id(assignment: Assignment) -> str:
    if assignment.url:
        return f"url:{assignment.url}"

    values = (
        assignment.type,
        assignment.title,
        assignment.course,
        assignment.start_at.isoformat() if assignment.start_at else "",
        assignment.end_at.isoformat() if assignment.end_at else "",
    )
    digest = hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def assignment_fingerprint(assignment: Assignment) -> str:
    values = (
        assignment.type,
        assignment.title,
        assignment.course,
        assignment.start_at.isoformat() if assignment.start_at else "",
        assignment.end_at.isoformat() if assignment.end_at else "",
        assignment.url or "",
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def current_assignment_ids(assignments: Sequence[Assignment]) -> set[str]:
    return {assignment_id(assignment) for assignment in assignments}


def find_new_assignments(
    assignments: Sequence[Assignment],
    previous_ids: set[str] | None,
) -> list[Assignment]:
    known = previous_ids or set()
    new_assignments: list[Assignment] = []
    added_ids: set[str] = set()

    for assignment in assignments:
        identifier = assignment_id(assignment)
        if identifier not in known and identifier not in added_ids:
            new_assignments.append(assignment)
            added_ids.add(identifier)
    return new_assignments


def _load_v1(data: dict[str, object]) -> NewAssignmentsState:
    assignment_ids = data.get("assignment_ids")
    if not isinstance(assignment_ids, list) or not all(
        isinstance(value, str) for value in assignment_ids
    ):
        raise StateError("新着課題の状態ファイルの形式が不正")
    return NewAssignmentsState(assignment_ids=set(assignment_ids))


def _load_v2(data: dict[str, object]) -> NewAssignmentsState:
    assignment_ids = data.get("assignment_ids")
    tasks = data.get("todoist_tasks")
    if (
        not isinstance(assignment_ids, list)
        or not all(isinstance(value, str) for value in assignment_ids)
        or not isinstance(tasks, dict)
    ):
        raise StateError("新着課題の状態ファイルの形式が不正")

    parsed_tasks: dict[str, TodoistTaskState] = {}
    for identifier, raw_task in tasks.items():
        if not isinstance(identifier, str) or not isinstance(raw_task, dict):
            raise StateError("新着課題の状態ファイルの形式が不正")
        task_id = raw_task.get("task_id")
        fingerprint = raw_task.get("fingerprint")
        completed = raw_task.get("completed")
        create_uuid = raw_task.get("create_command_uuid")
        temp_id = raw_task.get("temp_id")
        pending_commands = raw_task.get("pending_commands", {})
        if (
            (task_id is not None and not isinstance(task_id, str))
            or not isinstance(fingerprint, str)
            or not isinstance(completed, bool)
            or not isinstance(create_uuid, str)
            or not isinstance(temp_id, str)
            or not isinstance(pending_commands, dict)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in pending_commands.items()
            )
        ):
            raise StateError("新着課題の状態ファイルの形式が不正")
        parsed_tasks[identifier] = TodoistTaskState(
            task_id=task_id,
            fingerprint=fingerprint,
            completed=completed,
            create_command_uuid=create_uuid,
            temp_id=temp_id,
            pending_commands=dict(pending_commands),
        )
    return NewAssignmentsState(set(assignment_ids), parsed_tasks)


def load_state(path: Path) -> NewAssignmentsState:
    if not path.exists():
        return NewAssignmentsState()

    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(
            with_detail(
                "新着課題の状態ファイルを読み込めない",
                exception_type(exc),
            )
        ) from exc

    if not isinstance(data, dict):
        raise StateError("新着課題の状態ファイルの形式が不正")
    if data.get("version") == 1:
        return _load_v1(data)
    if data.get("version") == STATE_VERSION:
        return _load_v2(data)
    raise StateError("新着課題の状態ファイルの形式が不正")


def save_state(path: Path, state: NewAssignmentsState) -> None:
    directory = path.parent
    temporary_path: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            os.chmod(temporary_path, 0o600)
            json.dump(
                {
                    "version": STATE_VERSION,
                    "assignment_ids": sorted(state.assignment_ids),
                    "todoist_tasks": {
                        identifier: {
                            "task_id": task.task_id,
                            "fingerprint": task.fingerprint,
                            "completed": task.completed,
                            "create_command_uuid": task.create_command_uuid,
                            "temp_id": task.temp_id,
                            "pending_commands": task.pending_commands,
                        }
                        for identifier, task in sorted(state.todoist_tasks.items())
                    },
                },
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise StateError(
            with_detail(
                "新着課題の状態ファイルを保存できない",
                exception_type(exc),
            )
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
