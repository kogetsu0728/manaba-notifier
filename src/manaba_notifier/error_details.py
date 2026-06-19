from __future__ import annotations

import requests


def exception_type(exc: BaseException) -> str:
    return type(exc).__name__


def request_detail(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}"
    return exception_type(exc)


def with_detail(message: str, detail: str) -> str:
    return f"{message} ({detail})"
