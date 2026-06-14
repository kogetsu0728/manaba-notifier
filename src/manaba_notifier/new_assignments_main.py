from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from manaba_notifier.collector import collect_assignments
from manaba_notifier.config import (
    NewAssignmentsConfig,
    load_new_assignments_config,
)
from manaba_notifier.discord import (
    build_new_assignment_payloads,
    post_webhook,
)
from manaba_notifier.diagnostic_log import record_failure
from manaba_notifier.models import Assignment
from manaba_notifier.new_assignments_state import (
    NewAssignmentsState,
    TodoistTaskState,
    assignment_fingerprint,
    assignment_id,
    current_assignment_ids,
    find_new_assignments,
    load_state,
    save_state,
)
from manaba_notifier.runtime import run_job
from manaba_notifier.todoist import (
    MAX_COMMANDS,
    TodoistCommand,
    TodoistError,
    sync_commands,
    task_fields,
)

STATE_PATH = (
    Path.home()
    / ".local"
    / "state"
    / "manaba-notifier"
    / "new-assignments.json"
)


@dataclass(frozen=True)
class _Operation:
    identifier: str
    action: str
    fingerprint: str
    command: TodoistCommand
    pending_key: str | None = None


def _pending_uuid(task: TodoistTaskState, key: str) -> str:
    return task.pending_commands.setdefault(key, str(uuid.uuid4()))


def _create_operation(
    identifier: str,
    assignment: Assignment,
    task: TodoistTaskState,
    config: NewAssignmentsConfig,
) -> _Operation:
    fingerprint = assignment_fingerprint(assignment)
    if not task.create_command_uuid:
        task.create_command_uuid = str(uuid.uuid4())
    if not task.temp_id:
        task.temp_id = str(uuid.uuid5(uuid.UUID(task.create_command_uuid), "task"))
    return _Operation(
        identifier,
        "create",
        fingerprint,
        TodoistCommand(
            uuid=task.create_command_uuid,
            temp_id=task.temp_id,
            type="item_add",
            args=task_fields(
                assignment,
                config.todoist_project_id,
                config.timezone,
            ),
        ),
    )


def _todoist_operations(
    assignments: Sequence[Assignment],
    state: NewAssignmentsState,
    config: NewAssignmentsConfig,
) -> list[_Operation]:
    current = {assignment_id(item): item for item in assignments}
    operations: list[_Operation] = []

    for identifier, assignment in current.items():
        task = state.todoist_tasks.setdefault(identifier, TodoistTaskState())
        fingerprint = assignment_fingerprint(assignment)
        if task.task_id is None:
            operations.append(_create_operation(identifier, assignment, task, config))
            continue

        if task.completed:
            pending_key = "uncomplete"
            operations.append(
                _Operation(
                    identifier,
                    "uncomplete",
                    fingerprint,
                    TodoistCommand(
                        _pending_uuid(task, pending_key),
                        "item_uncomplete",
                        {"id": task.task_id},
                    ),
                    pending_key,
                )
            )

        if task.fingerprint != fingerprint:
            pending_key = f"update:{fingerprint}"
            fields = task_fields(
                assignment,
                config.todoist_project_id,
                config.timezone,
            )
            fields.pop("project_id")
            operations.append(
                _Operation(
                    identifier,
                    "update",
                    fingerprint,
                    TodoistCommand(
                        _pending_uuid(task, pending_key),
                        "item_update",
                        {"id": task.task_id, **fields},
                    ),
                    pending_key,
                )
            )

    for identifier, task in state.todoist_tasks.items():
        if identifier in current or task.task_id is None or task.completed:
            continue
        operations.append(
            _Operation(
                identifier,
                "close",
                task.fingerprint,
                TodoistCommand(
                    _pending_uuid(task, "close"),
                    "item_close",
                    {"id": task.task_id},
                ),
                "close",
            )
        )
    return operations


def _apply_success(
    operation: _Operation,
    task_ids: dict[str, str],
    state: NewAssignmentsState,
) -> bool:
    task = state.todoist_tasks[operation.identifier]
    if operation.action == "create":
        task_id = task_ids.get(task.temp_id)
        if task_id is None:
            return False
        task.task_id = task_id
        task.fingerprint = operation.fingerprint
        task.completed = False
    elif operation.action == "update":
        task.fingerprint = operation.fingerprint
    elif operation.action == "close":
        task.completed = True
    elif operation.action == "uncomplete":
        task.completed = False
    if operation.pending_key:
        task.pending_commands.pop(operation.pending_key, None)
    return True


def _sync_todoist(
    assignments: Sequence[Assignment],
    state: NewAssignmentsState,
    config: NewAssignmentsConfig,
) -> None:
    operations = _todoist_operations(assignments, state, config)
    if operations:
        save_state(STATE_PATH, state)

    failed = False
    for start in range(0, len(operations), MAX_COMMANDS):
        batch = operations[start : start + MAX_COMMANDS]
        result = sync_commands(
            config.todoist_api_token,
            [operation.command for operation in batch],
        )
        for operation in batch:
            if operation.command.uuid not in result.succeeded:
                failed = True
                continue
            if not _apply_success(operation, result.task_ids, state):
                failed = True
        save_state(STATE_PATH, state)

    if failed:
        raise TodoistError("Todoistの一部の課題を同期できなかった")


def _notify_discord(
    assignments: Sequence[Assignment],
    state: NewAssignmentsState,
    config: NewAssignmentsConfig,
) -> None:
    new_assignments = find_new_assignments(assignments, state.assignment_ids)
    for payload in build_new_assignment_payloads(new_assignments):
        post_webhook(config.new_assignments_discord_webhook_url, payload)
    state.assignment_ids = current_assignment_ids(assignments)
    save_state(STATE_PATH, state)


def _execute(config: NewAssignmentsConfig) -> None:
    assignments = collect_assignments(config)
    state = load_state(STATE_PATH)
    errors: list[Exception] = []

    try:
        _notify_discord(assignments, state, config)
    except Exception as exc:
        record_failure("new-assignments", "discord", exc)
        errors.append(exc)

    try:
        _sync_todoist(assignments, state, config)
    except Exception as exc:
        record_failure("new-assignments", "todoist", exc)
        errors.append(exc)

    if errors:
        raise errors[0]


def run() -> int:
    return run_job(
        load_config=load_new_assignments_config,
        execute=_execute,
        webhook_url=lambda config: config.new_assignments_discord_webhook_url,
        fallback_webhook_env="NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL",
        failure_label="manaba新着課題通知に失敗した",
        job_name="new-assignments",
    )


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
