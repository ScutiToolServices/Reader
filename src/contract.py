"""Tool result models. `message` is last: ember's generic formatter shows it first."""

from __future__ import annotations

from pydantic import BaseModel


class ParseResult(BaseModel):
    text: str
    pages: list[str]
    page_count: int
    cached: bool
    message: str
