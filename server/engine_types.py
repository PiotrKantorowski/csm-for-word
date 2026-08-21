from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    category: str
    value: str
    start: int
    end: int

@dataclass
class Replacement:
    category: str
    original: str
    placeholder: str
    count: int
