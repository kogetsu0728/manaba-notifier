from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from manaba_notifier.models import Assignment


def filter_assignments(
    assignments: Sequence[Assignment],
    now: datetime,
    within_days: int,
) -> list[Assignment]:
    deadline = now + timedelta(days=within_days)
    selected = [
        assignment
        for assignment in assignments
        if assignment.end_at is not None and now <= assignment.end_at <= deadline
    ]
    return sorted(selected, key=lambda assignment: assignment.end_at)
