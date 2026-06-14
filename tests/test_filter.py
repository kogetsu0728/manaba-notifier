from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from manaba_notifier.filter import filter_assignments
from manaba_notifier.models import Assignment


ZONE = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 6, 14, 12, 0, tzinfo=ZONE)


def _assignment(title: str, end_at: datetime | None) -> Assignment:
    return Assignment("レポート", title, "科目", None, end_at, None)


def test_filter_assignments_applies_boundaries_and_sorts() -> None:
    assignments = [
        _assignment("期限なし", None),
        _assignment("期限切れ", NOW - timedelta(minutes=1)),
        _assignment("期間外", NOW + timedelta(days=3, minutes=1)),
        _assignment("上限", NOW + timedelta(days=3)),
        _assignment("途中", NOW + timedelta(days=1)),
        _assignment("現在", NOW),
    ]

    selected = filter_assignments(assignments, NOW, 3)

    assert [assignment.title for assignment in selected] == ["現在", "途中", "上限"]

