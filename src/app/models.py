from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Expert(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "low"


class Skill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "low"
    enabled: bool = True


class RouteRequest(BaseModel):
    task: str = Field(min_length=1)
    task_id: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    excluded_skills: list[str] = Field(default_factory=list)
    preferred_expert: str | None = None
    constraints: dict[str, bool | str] = Field(default_factory=dict)
    max_skills: int = Field(default=3, ge=1, le=10)


class CandidateScore(BaseModel):
    id: str
    score: float
    reasons: list[str]


class RouteResponse(BaseModel):
    task_id: str | None = None
    expert: Expert
    skills: list[Skill]
    confidence: float
    needs_confirmation: bool
    fallback: bool = False
    reasons: list[str]
    candidates: list[CandidateScore]
