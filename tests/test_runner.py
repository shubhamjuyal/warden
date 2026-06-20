"""End-to-end runner behaviour through its HTTP surface, with a fake writer."""
import pytest
from fastapi.testclient import TestClient

from warden_common import ledger
from warden_common.db import session_scope
from warden_common.schemas import ActionType, IssueAction, ProposalPayload
from warden_runner import app as runner_module

from .fakes import FakeWriter


def _payload():
    return ProposalPayload(
        repo="acme/api",
        actions=[
            IssueAction(type=ActionType.LABEL, issue_number=1, value="severity:critical", rationale="r"),
            IssueAction(type=ActionType.ASSIGN, issue_number=1, value="alice", rationale="r"),
            IssueAction(type=ActionType.CLOSE, issue_number=2, value="1", rationale="dup"),
        ],
    )


@pytest.fixture()
def client(ledger_db):
    writer = FakeWriter()
    runner_module.set_writer(writer)
    with TestClient(runner_module.app) as c:
        yield c, writer
    runner_module.set_writer(None)


def test_execute_without_approval_is_refused(client):
    c, writer = client
    with session_scope() as s:
        pid = ledger.create_proposal(s, payload=_payload(), requested_by="u").id
    # No approval recorded; the agent forges a token and asks the runner to run.
    resp = c.post("/execute", json={"proposal_id": pid, "approval_token": "forged"})
    assert resp.status_code == 403
    assert "no such approval token" in resp.json()["detail"]
    assert writer.calls == []  # nothing touched GitHub


def test_execute_with_valid_approval_runs_and_records(client):
    c, writer = client
    with session_scope() as s:
        pid = ledger.create_proposal(s, payload=_payload(), requested_by="u").id
    with session_scope() as s:
        token = ledger.record_decision(
            s, proposal_id=pid, approver="boss", decision="approve"
        ).approval_token

    resp = c.post("/execute", json={"proposal_id": pid, "approval_token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["executed"]) == 3

    # The fake writer saw exactly the approved actions.
    kinds = [call[0] for call in writer.calls]
    assert kinds == ["add_labels", "add_assignees", "comment", "close_issue"]

    # And the audit trail recorded the execution.
    from warden_common.reads import list_audit

    with session_scope() as s:
        audit = list_audit(s)
    assert audit["chain_ok"] is True
    assert any(e["event_type"] == "proposal.executed" for e in audit["entries"])


def test_refusal_is_itself_audited(client):
    c, _ = client
    with session_scope() as s:
        pid = ledger.create_proposal(s, payload=_payload(), requested_by="u").id
    c.post("/execute", json={"proposal_id": pid, "approval_token": "forged"})

    from warden_common.reads import list_audit

    with session_scope() as s:
        audit = list_audit(s)
    assert any(e["event_type"] == "execute.refused" for e in audit["entries"])
    assert audit["chain_ok"] is True
