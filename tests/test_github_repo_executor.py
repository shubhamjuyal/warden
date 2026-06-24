"""The github_repo executor dispatches branch/commit/PR actions to the writer."""
from __future__ import annotations

from warden_common.schemas import Action
from warden_runner.executors.github_repo import GithubRepoExecutor

from .fakes import FakeWriter


def _exec() -> tuple[GithubRepoExecutor, FakeWriter]:
    w = FakeWriter()
    return GithubRepoExecutor(w), w


def test_create_branch_calls_writer():
    ex, w = _exec()
    action = Action(provider="github_repo", type="create_branch", target="fix/x",
                    args={"base": "main"}, rationale="r")
    ok, detail = ex.execute("acme/api", action)
    assert ok and "fix/x" in detail
    assert w.calls == [("create_branch", "acme/api", "fix/x", "main")]


def test_commit_file_passes_content_and_branch():
    ex, w = _exec()
    action = Action(provider="github_repo", type="commit_file", target="src/a.py",
                    args={"branch": "fix/x", "content": "BODY", "message": "msg"}, rationale="r")
    ok, _ = ex.execute("acme/api", action)
    assert ok
    assert w.calls == [("commit_file", "acme/api", "fix/x", "src/a.py", "BODY", "msg")]


def test_open_pr_returns_url_in_detail():
    ex, w = _exec()
    action = Action(provider="github_repo", type="open_pr", target="fix/x",
                    args={"base": "main", "title": "T", "body": "Fixes #1"}, rationale="r")
    ok, detail = ex.execute("acme/api", action)
    assert ok and "pull/1" in detail
    assert w.calls == [("open_pr", "acme/api", "fix/x", "main", "T", "Fixes #1")]


def test_unknown_operation_fails_cleanly():
    ex, _ = _exec()
    action = Action(provider="github_repo", type="rebase", target="x", rationale="r")
    ok, detail = ex.execute("acme/api", action)
    assert not ok and "unknown" in detail
