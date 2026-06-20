"""Executor for the ``github_issues`` provider — label / assign / close.

This is the runner-side counterpart to the triage capability. It is the only
place these GitHub writes are performed, using the runner's write-scoped client.
A different capability that writes elsewhere (Slack, Notion, Linear…) ships its
own executor alongside this one; this file does not need to change.
"""
from __future__ import annotations

from typing import Protocol

from warden_common.schemas import Action


class Writer(Protocol):
    def add_labels(self, repo: str, issue: int, labels: list[str]) -> None: ...
    def add_assignees(self, repo: str, issue: int, assignees: list[str]) -> None: ...
    def close_issue(self, repo: str, issue: int, *, reason: str = ...) -> None: ...
    def comment(self, repo: str, issue: int, body: str) -> None: ...


class GithubIssuesExecutor:
    provider = "github_issues"

    def __init__(self, writer: Writer):
        self._w = writer

    def execute(self, subject: str, action: Action) -> tuple[bool, str]:
        repo = subject  # for this provider the subject is "owner/repo"
        issue = int(action.target)
        if action.type == "label":
            self._w.add_labels(repo, issue, [action.value])
            return True, f"labeled #{issue} '{action.value}'"
        if action.type == "assign":
            self._w.add_assignees(repo, issue, [action.value])
            return True, f"assigned #{issue} -> {action.value}"
        if action.type == "close":
            if action.value:
                self._w.comment(
                    repo,
                    issue,
                    f"Closing as a duplicate of #{action.value}. "
                    f"— triaged by Warden, approved via the permission ledger.",
                )
            self._w.close_issue(repo, issue, reason="not_planned")
            return True, f"closed #{issue}" + (f" (dup of #{action.value})" if action.value else "")
        return False, f"unknown github_issues operation '{action.type}'"
