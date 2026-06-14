from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from manaba_notifier.scraper import ScraperError, parse_assignments


FIXTURE = Path(__file__).parent / "fixtures" / "assignments.html"


def test_parse_assignments() -> None:
    assignments = parse_assignments(
        FIXTURE.read_text(encoding="utf-8"),
        "https://manaba.example/ct/home_library_query",
        "Asia/Tokyo",
    )

    assert len(assignments) == 2
    first = assignments[0]
    assert first.type == "レポート"
    assert first.title == "第8回課題"
    assert first.course == "プログラミングチャレンジ"
    assert first.start_at == datetime(2026, 6, 10, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert first.end_at == datetime(2026, 6, 16, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert first.url == "https://manaba.example/ct/course_123_report_456"
    assert assignments[1].start_at is None
    assert assignments[1].end_at is None


def test_parse_assignments_requires_table() -> None:
    with pytest.raises(ScraperError, match="table.stdlist"):
        parse_assignments("<html></html>", "https://manaba.example/", "Asia/Tokyo")


def test_parse_assignments_rejects_invalid_datetime() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace(
        "2026-06-16 23:00", "2026/06/16 23:00"
    )

    with pytest.raises(ScraperError, match="日時を解析できない"):
        parse_assignments(html, "https://manaba.example/", "Asia/Tokyo")

