from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

import requests

from manaba_notifier.errors import NotifierError
from manaba_notifier.models import Assignment

MAX_EMBEDS = 10
COLOR_URGENT = 0xED4245
COLOR_SOON = 0xF57C00
COLOR_UPCOMING = 0xFEE75C
COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_NEW = 0x5865F2

WebhookPayload = dict[str, object]
Embed = dict[str, object]


class DiscordError(RuntimeError, NotifierError):
    """Raised when a Discord Webhook request fails."""


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _deadline_color(end_at: datetime, now: datetime) -> int:
    remaining = end_at - now
    if remaining <= timedelta(hours=24):
        return COLOR_URGENT
    if remaining <= timedelta(hours=48):
        return COLOR_SOON
    return COLOR_UPCOMING


def _deadline_text(end_at: datetime | None) -> str:
    if end_at is None:
        return "期限なし"
    unix_time = int(end_at.timestamp())
    return f"<t:{unix_time}:F>\n<t:{unix_time}:R>"


def _assignment_embed(
    assignment: Assignment,
    *,
    color: int,
    footer: str | None = None,
) -> Embed:
    embed: Embed = {
        "title": _truncate(assignment.title, 180),
        "color": color,
        "fields": [
            {
                "name": "締切",
                "value": _deadline_text(assignment.end_at),
                "inline": False,
            },
            {
                "name": "科目",
                "value": _truncate(assignment.course, 160) or "不明",
                "inline": True,
            },
            {
                "name": "種類",
                "value": _truncate(assignment.type, 80) or "不明",
                "inline": True,
            },
        ],
    }
    if assignment.url:
        embed["url"] = assignment.url
    if footer:
        embed["footer"] = {"text": footer}
    return embed


def _upcoming_assignment_embed(assignment: Assignment, now: datetime) -> Embed:
    if assignment.end_at is None:
        raise ValueError("通知対象の課題には期限が必要")
    return _assignment_embed(
        assignment,
        color=_deadline_color(assignment.end_at, now),
    )


def build_assignment_payload(
    assignments: Sequence[Assignment],
    within_days: int,
    now: datetime,
) -> WebhookPayload:
    if not assignments:
        return {
            "embeds": [
                {
                    "title": "manaba 未提出課題",
                    "description": f"期限が{within_days}日以内の未提出課題はなさそうです。",
                    "color": COLOR_SUCCESS,
                }
            ],
            "allowed_mentions": {"parse": []},
        }

    shown = assignments[:MAX_EMBEDS]
    summary = f"期限が{within_days}日以内の未提出課題: **{len(assignments)}件**"
    if len(assignments) > MAX_EMBEDS:
        summary += f"\n先頭{MAX_EMBEDS}件を表示しています。"

    return {
        "content": summary,
        "embeds": [
            _upcoming_assignment_embed(assignment, now) for assignment in shown
        ],
        "allowed_mentions": {"parse": []},
    }


def build_error_payload(reason: str) -> WebhookPayload:
    return {
        "embeds": [
            {
                "title": "manaba課題通知に失敗しました",
                "description": f"**原因**\n{_truncate(reason, 1000)}",
                "color": COLOR_ERROR,
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def build_new_assignment_payloads(
    assignments: Sequence[Assignment],
) -> list[WebhookPayload]:
    payloads: list[WebhookPayload] = []
    total = len(assignments)

    for start in range(0, total, MAX_EMBEDS):
        batch = assignments[start : start + MAX_EMBEDS]
        content = f"新しい未提出課題: **{total}件**"
        if total > MAX_EMBEDS:
            end = start + len(batch)
            content += f"\n{start + 1}〜{end}件目を表示しています。"
        payloads.append(
            {
                "content": content,
                "embeds": [
                    _assignment_embed(
                        assignment,
                        color=COLOR_NEW,
                        footer="manaba 新着課題",
                    )
                    for assignment in batch
                ],
                "allowed_mentions": {"parse": []},
            }
        )
    return payloads


def post_webhook(webhook_url: str, payload: Mapping[str, object]) -> None:
    try:
        response = requests.post(
            webhook_url,
            params={"wait": "true"},
            json=dict(payload),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DiscordError("Discord Webhookへの投稿に失敗した") from exc
