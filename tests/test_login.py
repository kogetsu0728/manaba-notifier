from unittest.mock import MagicMock, call

import pytest
from playwright.sync_api import Error as PlaywrightError

from manaba_notifier.config import Config
from manaba_notifier.login import LoginError, login


def test_login_fills_credentials_and_opens_assignments() -> None:
    config = Config(
        manaba_login_url="https://manaba.example/login",
        manaba_assignments_url="https://manaba.example/assignments",
        manaba_id="student-id",
        manaba_password="secret-password",
        deadline_assignments_discord_webhook_url=(
            "https://discord.example/webhook"
        ),
    )
    page = MagicMock()
    user_input = MagicMock()
    password_input = MagicMock()
    success_text = MagicMock()
    page.locator.side_effect = [user_input, password_input]
    page.get_by_text.return_value = success_text

    login(page, config)

    assert page.goto.call_args_list == [
        call(config.manaba_login_url, wait_until="load", timeout=60_000),
        call(
            config.manaba_assignments_url,
            wait_until="domcontentloaded",
            timeout=60_000,
        ),
    ]
    assert page.locator.call_args_list == [call("#username"), call("#password")]
    password_input.wait_for.assert_called_once_with(state="visible", timeout=60_000)
    user_input.fill.assert_called_once_with("student-id")
    password_input.fill.assert_called_once_with("secret-password")
    password_input.press.assert_called_once_with("Enter")
    page.wait_for_url.assert_called_once_with(
        "https://manaba.example/**",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    success_text.wait_for.assert_called_once_with(state="visible", timeout=60_000)


def _config() -> Config:
    return Config(
        manaba_login_url="https://manaba.example/login",
        manaba_assignments_url="https://manaba.example/assignments",
        manaba_id="student-id",
        manaba_password="secret-password",
        deadline_assignments_discord_webhook_url=(
            "https://discord.example/webhook"
        ),
    )


@pytest.mark.parametrize(
    ("failing_call", "message"),
    [
        ("login_page", "ログインページへの接続に失敗した"),
        ("login_form", "ログインページの構造が変更された可能性がある"),
        ("authentication", "ログインに失敗した"),
        ("assignments_page", "課題一覧ページへの接続に失敗した"),
        ("assignments_heading", "課題一覧ページの構造が変更された可能性がある"),
    ],
)
def test_login_reports_failure_stage(failing_call: str, message: str) -> None:
    page = MagicMock()
    user_input = MagicMock()
    password_input = MagicMock()
    success_text = MagicMock()
    page.locator.side_effect = [user_input, password_input]
    page.get_by_text.return_value = success_text

    if failing_call == "login_page":
        page.goto.side_effect = PlaywrightError("secret network details")
    elif failing_call == "login_form":
        password_input.wait_for.side_effect = PlaywrightError("secret page details")
    elif failing_call == "authentication":
        page.wait_for_url.side_effect = PlaywrightError("secret authentication details")
    elif failing_call == "assignments_page":
        page.goto.side_effect = [None, PlaywrightError("secret network details")]
    else:
        success_text.wait_for.side_effect = PlaywrightError("secret page details")

    with pytest.raises(LoginError, match=message) as exc_info:
        login(page, _config())

    assert "secret" not in str(exc_info.value)
