from __future__ import annotations

import os

from manaba_notifier.diagnostic_log import record_failure
from manaba_notifier.runtime import run_job


def test_record_failure_excludes_exception_message_and_external_frames(
    monkeypatch,
    tmp_path,
) -> None:
    secret = "https://discord.example/webhook/secret-token"
    monkeypatch.setattr(
        "manaba_notifier.diagnostic_log.LOG_DIRECTORY",
        tmp_path,
    )

    try:
        raise RuntimeError(secret)
    except RuntimeError as exc:
        record_failure("deadline", "execute", exc)

    log_path = tmp_path / "deadline-errors.log"
    content = log_path.read_text(encoding="utf-8")
    assert "builtins.RuntimeError" in content
    assert "reason=予期しないエラーが発生した" in content
    assert secret not in content
    assert "test_diagnostic_log.py" not in content
    assert os.stat(tmp_path).st_mode & 0o777 == 0o700
    assert os.stat(log_path).st_mode & 0o777 == 0o600


def test_run_job_records_application_frame_and_stage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "manaba_notifier.diagnostic_log.LOG_DIRECTORY",
        tmp_path,
    )
    monkeypatch.setattr(
        "manaba_notifier.runtime.notify_failure",
        lambda url, reason: None,
    )

    result = run_job(
        load_config=lambda: object(),
        execute=lambda config: (_ for _ in ()).throw(RuntimeError("private")),
        webhook_url=lambda config: "",
        fallback_webhook_env="TEST_WEBHOOK_URL",
        failure_label="テスト失敗",
        job_name="deadline",
    )

    content = (tmp_path / "deadline-errors.log").read_text(encoding="utf-8")
    assert result == 1
    assert "job=deadline" in content
    assert "stage=execute" in content
    assert "manaba_notifier/runtime.py" in content
    assert "private" not in content


def test_record_failure_ignores_log_write_errors(monkeypatch, tmp_path) -> None:
    occupied_path = tmp_path / "not-a-directory"
    occupied_path.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(
        "manaba_notifier.diagnostic_log.LOG_DIRECTORY",
        occupied_path,
    )

    record_failure("deadline", "execute", RuntimeError("private"))
