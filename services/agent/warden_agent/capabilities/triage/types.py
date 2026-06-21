"""Triage-specific types.

These describe the agent's *internal* reasoning output for the triage
capability. They are not part of the platform core (other capabilities have
their own internal shapes); only the resulting generic ``Action``s are.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

#: The standard GitHub issue labels. Triage picks exactly one per issue.
Label = Literal[
    "bug",
    "documentation",
    "duplicate",
    "enhancement",
    "good first issue",
    "invalid",
    "question",
]

#: Human-readable meaning of each label, shown to the model and on the card.
LABEL_DESCRIPTIONS: dict[str, str] = {
    "bug": "Something isn't working",
    "documentation": "Improvements or additions to documentation",
    "duplicate": "This issue or pull request already exists",
    "enhancement": "New feature or request",
    "good first issue": "Good for newcomers",
    "invalid": "This doesn't seem right",
    "question": "Further information is requested",
}


class IssueClassification(BaseModel):
    issue_number: int
    #: exactly one of the standard labels above
    label: Label
    #: a repo collaborator to assign, or None if no clear fit
    assignee: str | None = None
    rationale: str = ""
    evidence: str = ""
