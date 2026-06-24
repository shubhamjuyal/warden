"""End-to-end: an approved fix proposal makes the runner write branch/commit/PR.

This is the happy path the guardrail test's #3 is the mirror of: WITH a real
human approval in the ledger, the runner executes the fixer's actions in order
against the (faked) write client. Proves the new github_repo provider is wired
all the way through execute -> registry -> executor -> writer.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from warden_common import ledger
from warden_common.db import session_scope
from warden_common.schemas import Action, ProposalPayload
from warden_runner import app as runner_module

from .fakes import FakeWriter


def test_approved_fix_executes_branch_commit_pr_in_order(ledger_db):
    writer = FakeWriter()
    runner_module.set_writer(writer)

    payload = ProposalPayload(
        capability="fixer",
        subject="acme/api",
        actions=[
            Action(provider="github_repo", type="create_branch", target="fix/login",
                   args={"base": "main"}, rationale="branch for the fix"),
            Action(provider="github_repo", type="commit_file", target="src/auth.py",
                   args={"branch": "fix/login", "content": "fixed body", "message": "fix NPE"},
                   rationale="apply the fix"),
            Action(provider="github_repo", type="open_pr", target="fix/login",
                   args={"base": "main", "title": "Fix login NPE", "body": "Fixes #1"},
                   rationale="open the PR"),
        ],
    )

    # Propose, then a human approves -> a real approval token in the ledger.
    with session_scope() as s:
        pid = ledger.create_proposal(s, payload=payload, requested_by="dev").id
    with session_scope() as s:
        token = ledger.record_decision(
            s, proposal_id=pid, approver="maintainer", decision="approve"
        ).approval_token

    with TestClient(runner_module.app) as c:
        resp = c.post("/execute", json={"proposal_id": pid, "approval_token": token})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # The writes happened in dependency order: branch, then commit, then PR.
    assert writer.calls == [
        ("create_branch", "acme/api", "fix/login", "main"),
        ("commit_file", "acme/api", "fix/login", "src/auth.py", "fixed body", "fix NPE"),
        ("open_pr", "acme/api", "fix/login", "main", "Fix login NPE", "Fixes #1"),
    ]

    runner_module.set_writer(None)
