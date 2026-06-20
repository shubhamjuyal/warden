"""The execution gate is the security-critical surface. Exercise every path."""
import datetime as dt

import pytest

from warden_common import ledger
from warden_common.db import session_scope
from warden_common.ledger import ApprovalError
from warden_common.models import Approval
from warden_common.schemas import ActionType, IssueAction, ProposalPayload


def _payload():
    return ProposalPayload(
        repo="acme/api",
        actions=[
            IssueAction(type=ActionType.LABEL, issue_number=1, value="bug", rationale="r"),
        ],
    )


def _new_proposal(session, user="u1"):
    return ledger.create_proposal(session, payload=_payload(), requested_by=user)


def test_happy_path_approve_then_validate(ledger_db):
    with session_scope() as s:
        p = _new_proposal(s)
        pid = p.id
    with session_scope() as s:
        appr = ledger.record_decision(s, proposal_id=pid, approver="boss", decision="approve")
        token = appr.approval_token
    with session_scope() as s:
        proposal, approval = ledger.validate_for_execution(
            s, proposal_id=pid, approval_token=token
        )
        assert proposal.id == pid
        assert approval.approval_token == token


def test_no_token_is_refused(ledger_db):
    with session_scope() as s:
        pid = _new_proposal(s).id
    with session_scope() as s:
        with pytest.raises(ApprovalError, match="no such approval token"):
            ledger.validate_for_execution(s, proposal_id=pid, approval_token="made-up")


def test_denied_proposal_cannot_execute(ledger_db):
    with session_scope() as s:
        pid = _new_proposal(s).id
    with session_scope() as s:
        appr = ledger.record_decision(s, proposal_id=pid, approver="boss", decision="deny")
        assert appr is None  # deny yields no approval/token at all


def test_token_bound_to_its_own_proposal(ledger_db):
    with session_scope() as s:
        pid_a = _new_proposal(s, "a").id
        pid_b = _new_proposal(s, "b").id
    with session_scope() as s:
        token_a = ledger.record_decision(
            s, proposal_id=pid_a, approver="boss", decision="approve"
        ).approval_token
    with session_scope() as s:
        # Using A's token to authorise B must fail.
        with pytest.raises(ApprovalError, match="does not match"):
            ledger.validate_for_execution(s, proposal_id=pid_b, approval_token=token_a)


def test_actions_changed_after_approval_is_refused(ledger_db):
    with session_scope() as s:
        p = _new_proposal(s)
        pid = p.id
    with session_scope() as s:
        token = ledger.record_decision(
            s, proposal_id=pid, approver="boss", decision="approve"
        ).approval_token
    # Simulate tampering: the proposal's payload_hash is mutated post-approval.
    with session_scope() as s:
        from warden_common.models import Proposal

        s.get(Proposal, pid).payload_hash = "deadbeef"
    with session_scope() as s:
        with pytest.raises(ApprovalError, match="actions changed"):
            ledger.validate_for_execution(s, proposal_id=pid, approval_token=token)


def test_expired_time_limited_approval_is_refused(ledger_db):
    with session_scope() as s:
        pid = _new_proposal(s).id
    with session_scope() as s:
        appr = ledger.record_decision(
            s, proposal_id=pid, approver="boss", decision="approve", time_limit_minutes=5
        )
        token = appr.approval_token
        # Force it into the past.
        s.get(Approval, appr.id).expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    with session_scope() as s:
        with pytest.raises(ApprovalError, match="expired"):
            ledger.validate_for_execution(s, proposal_id=pid, approval_token=token)


def test_one_time_approval_consumed_after_use(ledger_db):
    with session_scope() as s:
        pid = _new_proposal(s).id
    with session_scope() as s:
        token = ledger.record_decision(
            s, proposal_id=pid, approver="boss", decision="approve_once"
        ).approval_token
    with session_scope() as s:
        proposal, approval = ledger.validate_for_execution(
            s, proposal_id=pid, approval_token=token
        )
        ledger.mark_executed(s, proposal=proposal, approval=approval, results=[], actor="runner")
    with session_scope() as s:
        with pytest.raises(ApprovalError, match="already executed"):
            ledger.validate_for_execution(s, proposal_id=pid, approval_token=token)


def test_standing_rule_auto_approves_matching_proposal(ledger_db):
    # First proposal gets a standing-rule decision, which lays down the rule.
    with session_scope() as s:
        pid1 = _new_proposal(s).id
    with session_scope() as s:
        ledger.record_decision(s, proposal_id=pid1, approver="boss", decision="standing_rule")
    # A later proposal in the same repo can be auto-approved with no human.
    with session_scope() as s:
        p2 = _new_proposal(s)
        appr = ledger.find_standing_approval(s, p2)
        assert appr is not None
        assert appr.approver == "standing-rule"
