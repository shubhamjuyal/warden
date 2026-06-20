"""Triage-specific types.

These describe the agent's *internal* reasoning output for the triage
capability. They are not part of the platform core (other capabilities have
their own internal shapes); only the resulting generic ``Action``s are.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Severity = Literal["critical", "high", "medium", "low"]


class IssueClassification(BaseModel):
    issue_number: int
    severity: Severity
    area: str                       # suggested area/team label, e.g. "backend"
    suggested_labels: list[str] = []
    suggested_assignee: str | None = None
    duplicate_of: int | None = None
    rationale: str = ""
    evidence: str = ""
