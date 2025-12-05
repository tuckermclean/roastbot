from __future__ import annotations

from dataclasses import dataclass
from typing import List, Iterable

from pydantic import BaseModel, Field, ValidationError


class RoastSchema(BaseModel):
    summary: str = Field(default_factory=str)
    issues: List[str] = Field(default_factory=list)
    praise: str = Field(default_factory=str)
    one_killer_roast_line: str = Field(default="This code trips over its own abstractions.")


@dataclass
class ParsedRoast:
    summary: str
    issues: List[str]
    praise: str
    one_killer_roast_line: str


def coerce_roast_json(data: dict) -> ParsedRoast:
    try:
        model = RoastSchema.model_validate(data or {})
    except ValidationError:
        model = RoastSchema()  # all defaults
    return ParsedRoast(
        summary=model.summary.strip(),
        issues=model.issues,
        praise=model.praise.strip(),
        one_killer_roast_line=model.one_killer_roast_line.strip() or "This code trips over its own abstractions.",
    )
