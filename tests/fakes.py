"""Test doubles for the agent's collaborators."""
from __future__ import annotations

from warden_agent.capabilities.triage.github_read import Issue
from warden_agent.capabilities.triage.types import IssueClassification


class FakeReader:
    """Stands in for GitHubReadClient with canned issues + collaborators."""

    def __init__(self, issues: list[dict], assignees: list[str] | None = None):
        self._issues = [Issue(i) for i in issues]
        self._assignees = assignees if assignees is not None else ["alice", "bob", "carol"]

    def list_open_issues(self, repo: str, *, limit: int = 50) -> list[Issue]:
        return self._issues[:limit]

    def list_assignees(self, repo: str, *, limit: int = 100) -> list[str]:
        return self._assignees[:limit]

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        pass


class FakeRepoReader:
    """Stands in for GitHubRepoReader with canned repository data — no network."""

    def __init__(self, files: dict[str, str] | None = None):
        # path -> file text, used by read_file / browse_dir.
        self._files = files if files is not None else {"README.md": "# Acme API\nHello."}

    def repo_overview(self, repo: str) -> dict:
        return {
            "full_name": repo,
            "description": "the acme api",
            "default_branch": "main",
            "language": "Python",
            "stars": 7,
            "topics": ["api"],
            "license": "MIT",
            "pushed_at": "2026-06-01T00:00:00Z",
            "archived": False,
        }

    def list_branches(self, repo: str, *, limit: int = 50) -> list[str]:
        return ["main", "dev"][:limit]

    def browse_dir(self, repo, path="", ref=None, *, limit: int = 200) -> list[dict]:
        return [
            {"name": p, "type": "file", "size": len(t), "path": p}
            for p, t in self._files.items()
        ][:limit]

    def read_file(self, repo, path, ref=None, *, max_bytes: int = 100_000) -> dict:
        if path not in self._files:
            return {"error": f"file '{path}' not found in {repo}"}
        text = self._files[path]
        return {"path": path, "size": len(text), "truncated": False, "content": text}

    def list_issues(self, repo, state="open", *, limit: int = 100) -> dict:
        issues = [
            {"number": 1, "title": "Bug A", "state": "open", "labels": [], "author": "alice", "comments": 0},
            {"number": 2, "title": "Bug B", "state": "open", "labels": ["bug"], "author": "bob", "comments": 3},
        ]
        return {"state": state, "count": len(issues), "capped": False, "issues": issues}

    def search_code(self, repo, query, *, limit: int = 20) -> list[dict]:
        return [
            {"path": p, "name": p, "html_url": f"https://github.com/{repo}/blob/main/{p}"}
            for p, t in self._files.items()
            if query in t
        ][:limit]

    def recent_commits(self, repo, ref=None, path=None, *, limit: int = 20) -> list[dict]:
        return [{"sha": "abc1234", "message": "init", "author": "alice", "date": "2026-06-01T00:00:00Z"}][:limit]

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        pass


class FakeClassifier:
    """Returns predetermined classifications (no LLM call)."""

    def __init__(self, items: list[IssueClassification]):
        self._items = items

    def classify(
        self, repo: str, issues: list[dict], assignees: list[str]
    ) -> list[IssueClassification]:
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
        issue_number=1, label="bug", assignee="alice",
        rationale="auth crash", evidence="NPE in AuthService",
    ),
    IssueClassification(
        issue_number=2, label="duplicate",
        rationale="dup of #1", evidence="Same NPE as #1",
    ),
    IssueClassification(
        issue_number=3, label="documentation",
        rationale="doc typo", evidence="README has a typo",
    ),
]
