"""Executor for the ``github_repo`` provider — branch / commit / open PR.

The runner-side counterpart to the fixer's write tools. It performs the actual
GitHub writes for a fix, using the runner's write-scoped client, and only ever
runs after a human has approved the proposal (the gate in ``app.py``). The
fixer's bundled proposal lists these actions in order — create_branch, then
commit_file(s), then open_pr — and the generic loop executes them in that order.
"""
from __future__ import annotations

from typing import Protocol

from warden_common.schemas import Action


class RepoWriter(Protocol):
    def create_branch(self, repo: str, branch: str, base: str = ...) -> None: ...
    def commit_file(self, repo: str, branch: str, path: str, content: str, message: str) -> None: ...
    def open_pr(self, repo: str, head: str, base: str = ..., title: str = ..., body: str = ...) -> str: ...


class GithubRepoExecutor:
    provider = "github_repo"

    def __init__(self, writer: RepoWriter):
        self._w = writer

    def execute(self, subject: str, action: Action) -> tuple[bool, str]:
        repo = subject  # the subject is "owner/repo"
        args = action.args

        if action.type == "create_branch":
            branch = action.target
            self._w.create_branch(repo, branch, args.get("base", ""))
            return True, f"created branch '{branch}'"

        if action.type == "commit_file":
            path = action.target
            branch = args.get("branch", "")
            self._w.commit_file(
                repo, branch, path, args.get("content", ""), args.get("message", "")
            )
            return True, f"committed '{path}' on '{branch}'"

        if action.type == "open_pr":
            head = action.target
            url = self._w.open_pr(
                repo,
                head,
                args.get("base", ""),
                args.get("title", ""),
                args.get("body", ""),
            )
            return True, f"opened PR from '{head}'" + (f": {url}" if url else "")

        return False, f"unknown github_repo operation '{action.type}'"
