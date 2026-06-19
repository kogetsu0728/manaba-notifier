from __future__ import annotations

from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from manaba_notifier.config import ManabaConfig
from manaba_notifier.error_details import exception_type, with_detail
from manaba_notifier.errors import NotifierError


class LoginError(RuntimeError, NotifierError):
    """Raised when manaba authentication does not complete successfully."""


LOGIN_TIMEOUT_MS = 60_000


def login(page: Page, config: ManabaConfig) -> None:
    try:
        page.goto(
            config.manaba_login_url,
            wait_until="load",
            timeout=LOGIN_TIMEOUT_MS,
        )
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise LoginError(
            with_detail("ログインページへの接続に失敗した", exception_type(exc))
        ) from exc

    try:
        user_input = page.locator("#username")
        password_input = page.locator("#password")
        password_input.wait_for(state="visible", timeout=LOGIN_TIMEOUT_MS)
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise LoginError(
            with_detail(
                "ログインページの構造が変更された可能性がある",
                exception_type(exc),
            )
        ) from exc

    try:
        user_input.fill(config.manaba_id)
        password_input.fill(config.manaba_password)
        password_input.press("Enter")

        assignments_url = urlsplit(config.manaba_assignments_url)
        page.wait_for_url(
            f"{assignments_url.scheme}://{assignments_url.netloc}/**",
            wait_until="domcontentloaded",
            timeout=LOGIN_TIMEOUT_MS,
        )
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise LoginError(
            with_detail("ログインに失敗した", exception_type(exc))
        ) from exc

    try:
        page.goto(
            config.manaba_assignments_url,
            wait_until="domcontentloaded",
            timeout=LOGIN_TIMEOUT_MS,
        )
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise LoginError(
            with_detail("課題一覧ページへの接続に失敗した", exception_type(exc))
        ) from exc

    try:
        page.get_by_text("未提出の課題一覧", exact=False).wait_for(
            state="visible",
            timeout=LOGIN_TIMEOUT_MS,
        )
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise LoginError(
            with_detail(
                "課題一覧ページの構造が変更された可能性がある",
                exception_type(exc),
            )
        ) from exc
