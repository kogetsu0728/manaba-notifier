from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Page

from manaba_notifier.errors import NotifierError
from manaba_notifier.models import Assignment


class ScraperError(RuntimeError, NotifierError):
    """Raised when the assignments page cannot be parsed."""


def _text(element: Tag | None) -> str:
    return element.get_text(" ", strip=True) if element is not None else ""


def _parse_datetime(value: str, timezone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ScraperError("課題一覧の日時を解析できない") from exc
    return parsed.replace(tzinfo=timezone)


def _parse_row(row: Tag, base_url: str, timezone: ZoneInfo) -> Assignment:
    cells = row.find_all("td", recursive=False)
    title_link = row.select_one(".myassignments-title a")
    course_link = row.select_one(".mycourse-title a")
    if not cells or title_link is None or course_link is None:
        raise ScraperError("課題一覧の行に必要な項目が見つからない")

    periods = row.select("td.td-period")
    start_text = _text(periods[0]) if periods else ""
    end_text = _text(periods[1]) if len(periods) > 1 else ""
    href = title_link.get("href")

    return Assignment(
        type=_text(cells[0]),
        title=_text(title_link),
        course=_text(course_link),
        start_at=_parse_datetime(start_text, timezone),
        end_at=_parse_datetime(end_text, timezone),
        url=urljoin(base_url, href) if isinstance(href, str) and href else None,
    )


def parse_assignments(html: str, base_url: str, timezone: str) -> list[Assignment]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.stdlist")
    if table is None:
        raise ScraperError("課題一覧テーブル table.stdlist が見つからない")

    zone = ZoneInfo(timezone)
    rows = table.select("tr.row0, tr.row1")
    return [_parse_row(row, base_url, zone) for row in rows]


def scrape_assignments(page: Page, timezone: str) -> list[Assignment]:
    if page.locator("table.stdlist").count() == 0:
        raise ScraperError("課題一覧テーブル table.stdlist が見つからない")
    return parse_assignments(page.content(), page.url, timezone)
