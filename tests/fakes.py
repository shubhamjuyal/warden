"""Test doubles for the agent's collaborators."""
from __future__ import annotations

from warden_agent.github_read import Issue
from warden_common.schemas import IssueClassification


class FakeReader:
    """Stands in for GitHubReadClient with canned issues."""

    def __init__(self, issues: list[dict]):
        self._issues = [Issue(i) for i in issues]

    def list_open_issues(self, repo: str, *, limit: int = 50) -> list[Issue]:
        return self._issues[:limit]

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        pass


class FakeClassifier:
    """Returns predetermined classifications (no LLM call)."""

    def __init__(self, items: list[IssueClassification]):
        self._items = items

    def classify(self, repo: str, issues: list[dict]) -> list[IssueClassification]:
        # Only classify issues we were actually given, mirroring the real one.
        nums = {i["number"] for i in issues}
        return [c for c in self._items if c.issue_number in nums]


class FakeWriter:
    """Records GitHub writes instead of performing them."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def add_labels(self, repo, issue, labels):
        self.calls.append(("add_labels", repo, issue, tuple(labels)))

    def add_assignees(self, repo, issue, assignees):
        self.calls.append(("add_assignees", repo, issue, tuple(assignees)))

    def close_issue(self, repo, issue, *, reason="not_planned"):
        self.calls.append(("close_issue", repo, issue, reason))

    def comment(self, repo, issue, body):
        self.calls.append(("comment", repo, issue, body))


SAMPLE_ISSUES = [
    {"number": 1, "title": "App crashes on login", "body": "NPE in AuthService", "labels": [], "user": {"login": "alice"}},
    {"number": 2, "title": "Login crash", "body": "Same NPE as #1", "labels": [], "user": {"login": "bob"}},
    {"number": 3, "title": "Typo in docs", "body": "README has a typo", "labels": [], "user": {"login": "carol"}},
]

SAMPLE_CLASSIFICATIONS = [
    IssueClassification(
        issue_number=1, severity="critical", area="auth",
        suggested_labels=["bug"], suggested_assignee="alice",
        rationale="auth crash", evidence="NPE in AuthService",
    ),
    IssueClassification(
        issue_number=2, severity="critical", area="auth",
        suggested_labels=["bug"], duplicate_of=1,
        rationale="dup of #1", evidence="Same NPE as #1",
    ),
    IssueClassification(
        issue_number=3, severity="low", area="docs",
        suggested_labels=["documentation"],
        rationale="doc typo", evidence="README has a typo",
    ),
]
