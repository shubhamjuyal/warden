"""The fixer's action builders map a fix onto provider-agnostic Actions.

Pure unit tests — no Slack, no GitHub. They pin down that bulky parameters (file
content, PR body, base branch) ride in ``args`` and not in the fields the Slack
approval card renders.
"""
from __future__ import annotations

from warden_agent.capabilities.fixer import actions as fixer


def test_branch_action_carries_base_in_args():
    a = fixer.branch_action("fix/login", base="main")
    assert a.provider == "github_repo"
    assert a.type == "create_branch"
    assert a.target == "fix/login"
    assert a.args == {"base": "main"}


def test_commit_action_keeps_content_out_of_rendered_fields():
    a = fixer.commit_action("fix/login", "src/auth.py", "FULL FILE BODY", "fix NPE")
    assert a.type == "commit_file"
    assert a.target == "src/auth.py"
    # content lives in args, never in value (so it can't bloat the Slack card)
    assert a.args["content"] == "FULL FILE BODY"
    assert a.args["branch"] == "fix/login"
    assert a.args["message"] == "fix NPE"
    assert "FULL FILE BODY" not in a.value


def test_pr_action_carries_title_and_body_in_args():
    a = fixer.pr_action("fix/login", base="main", title="Fix login", body="Fixes #12")
    assert a.type == "open_pr"
    assert a.target == "fix/login"
    assert a.args == {"base": "main", "title": "Fix login", "body": "Fixes #12"}
