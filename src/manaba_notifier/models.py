from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Assignment:
    type: str
    title: str
    course: str
    start_at: datetime | None
    end_at: datetime | None
    url: str | None
