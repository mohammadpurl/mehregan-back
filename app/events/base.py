from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class DomainEvent:
    name: str
    payload: dict
    occurred_at: datetime
