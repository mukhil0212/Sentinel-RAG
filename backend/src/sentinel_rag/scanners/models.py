from __future__ import annotations

from pydantic import BaseModel


class Finding(BaseModel):
    id: str
    tool: str
    severity: str
    title: str
    description: str
    recommendation: str
    file_path: str | None = None
    line: int | None = None
    raw: dict | None = None
