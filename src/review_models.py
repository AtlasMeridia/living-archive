"""Pydantic model for human review overlay files."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ReviewDecision(BaseModel):
    status: Literal["approved", "corrected", "skipped"]
    reviewed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    corrected_date: str | None = None
    corrected_description_en: str | None = None
    corrected_description_zh: str | None = None
    notes: str | None = None
