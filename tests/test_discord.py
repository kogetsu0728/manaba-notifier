from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests

from manaba_notifier.discord import (
    COLOR_ERROR,
    COLOR_NEW,
    COLOR_SOON,
    COLOR_SUCCESS,
    COLOR_UPCOMING,
    COLOR_URGENT,
    DiscordError,
    build_assignment_payload,
    build_error_payload,
    build_new_assignment_payloads,
    post_webhook,
)
from manaba_notifier.models import Assignment


ZONE = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 6, 14, 12, 0, tzinfo=ZONE)


def _assignment(
    title: str = "第8回課題",
    *,
    end_at: datetime | None = None,
) -> Assignment:
    return Assignment(
        type="レポート",
        title=title,
        course="プログラミングチャレンジ",
        start_at=None,
        end_at=end_at or NOW + timedelta(days=2),
        url="https://manaba.example/assignment",
    )


def test_build_assignment_payload_formats_rich_embed() -> None:
    assignment = _assignment()

    payload = build_assignment_payload([assignment], 3, NOW)

    assert payload["content"] == "期限が3日以内の未提出課題: **1件**"
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]
    assert embed["title"] == "第8回課題"
    assert embed["url"] == "https://manaba.example/assignment"
    assert embed["color"] == COLOR_SOON
    assert embed["fields"] == [
        {
            "name": "締切",
            "value": f"<t:{int(assignment.end_at.timestamp())}:F>\n"
            f"<t:{int(assignment.end_at.timestamp())}:R>",
            "inline": False,
        },
        {"name": "科目", "value": "プログラミングチャレンジ", "inline": True},
        {"name": "種類", "value": "レポート", "inline": True},
    ]


@pytest.mark.parametrize(
    ("remaining", "color"),
    [
        (timedelta(hours=24), COLOR_URGENT),
        (timedelta(hours=24, seconds=1), COLOR_SOON),
        (timedelta(hours=48), COLOR_SOON),
        (timedelta(hours=48, seconds=1), COLOR_UPCOMING),
    ],
)
def test_build_assignment_payload_colors_by_deadline(
    remaining: timedelta,
    color: int,
) -> None:
    payload = build_assignment_payload(
        [_assignment(end_at=NOW + remaining)],
        3,
        NOW,
    )

    assert payload["embeds"][0]["color"] == color


def test_build_assignment_payload_formats_empty_result() -> None:
    payload = build_assignment_payload([], 3, NOW)

    assert payload == {
        "embeds": [
            {
                "title": "manaba 未提出課題",
                "description": "期限が3日以内の未提出課題はなさそうです。",
                "color": COLOR_SUCCESS,
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def test_build_assignment_payload_limits_embeds() -> None:
    assignments = [_assignment(f"課題{i}") for i in range(12)]

    payload = build_assignment_payload(assignments, 3, NOW)

    assert len(payload["embeds"]) == 10
    assert payload["embeds"][-1]["title"] == "課題9"
    assert "先頭10件" in payload["content"]


def test_build_assignment_payload_truncates_long_values() -> None:
    assignment = Assignment(
        type="種" * 100,
        title="題" * 200,
        course="科" * 200,
        start_at=None,
        end_at=NOW + timedelta(days=3),
        url=None,
    )

    embed = build_assignment_payload([assignment], 3, NOW)["embeds"][0]

    assert len(embed["title"]) == 180
    assert len(embed["fields"][1]["value"]) == 160
    assert len(embed["fields"][2]["value"]) == 80
    assert "url" not in embed


def test_build_error_payload_formats_error_embed() -> None:
    payload = build_error_payload("ログインできない")

    assert payload == {
        "embeds": [
            {
                "title": "manaba課題通知に失敗しました",
                "description": "**原因**\nログインできない",
                "color": COLOR_ERROR,
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def test_build_new_assignment_payloads_formats_deadline_and_no_deadline() -> None:
    with_deadline = _assignment("締切あり")
    without_deadline = Assignment(
        type="アンケート",
        title="締切なし",
        course="情報基礎",
        start_at=None,
        end_at=None,
        url=None,
    )

    payloads = build_new_assignment_payloads([with_deadline, without_deadline])

    assert len(payloads) == 1
    assert payloads[0]["content"] == "新しい未提出課題: **2件**"
    assert payloads[0]["allowed_mentions"] == {"parse": []}
    first, second = payloads[0]["embeds"]
    assert first["color"] == COLOR_NEW
    assert first["fields"][0]["value"].startswith("<t:")
    assert second["fields"][0]["value"] == "期限なし"
    assert "url" not in second


def test_build_new_assignment_payloads_splits_all_assignments() -> None:
    assignments = [_assignment(f"課題{i}") for i in range(23)]

    payloads = build_new_assignment_payloads(assignments)

    assert [len(payload["embeds"]) for payload in payloads] == [10, 10, 3]
    assert payloads[0]["embeds"][0]["title"] == "課題0"
    assert payloads[-1]["embeds"][-1]["title"] == "課題22"
    assert "1〜10件目" in payloads[0]["content"]
    assert "21〜23件目" in payloads[-1]["content"]


def test_build_new_assignment_payloads_returns_empty_for_no_new_items() -> None:
    assert build_new_assignment_payloads([]) == []


def test_post_webhook_posts_payload_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

    calls: list[tuple[str, dict[str, str], dict[str, object], int]] = []

    def fake_post(
        url: str,
        params: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> Response:
        calls.append((url, params, json, timeout))
        return Response()

    monkeypatch.setattr("manaba_notifier.discord.requests.post", fake_post)
    payload = {"content": "message"}

    post_webhook("https://discord.example/secret", payload)

    assert calls == [
        (
            "https://discord.example/secret",
            {"wait": "true"},
            payload,
            30,
        )
    ]


def test_post_webhook_hides_url_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_url = "https://discord.example/webhook-secret"

    def fake_post(*args: object, **kwargs: object) -> None:
        raise requests.Timeout(f"timeout for {secret_url}")

    monkeypatch.setattr("manaba_notifier.discord.requests.post", fake_post)

    with pytest.raises(DiscordError) as captured:
        post_webhook(secret_url, {"content": "message"})

    assert secret_url not in str(captured.value)
    assert "Timeout" in str(captured.value)


def test_post_webhook_reports_http_status_without_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 429
        text = "rate limit detail"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("rate limit detail", response=self)

    monkeypatch.setattr(
        "manaba_notifier.discord.requests.post",
        lambda *args, **kwargs: Response(),
    )

    with pytest.raises(DiscordError) as captured:
        post_webhook("https://discord.example/webhook-secret", {"content": "message"})

    assert "HTTP 429" in str(captured.value)
    assert "rate limit detail" not in str(captured.value)
    assert "webhook-secret" not in str(captured.value)
