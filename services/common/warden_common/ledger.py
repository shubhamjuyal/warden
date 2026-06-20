"""The permission ledger — proposals, approvals, standing rules, and the
append-only audit trail.

This module is the *only* sanctioned way to write to the ledger. The runner's
execution gate (:func:`validate_for_execution`) lives here too, so the rule
"nothing executes without a valid, unexpired, action-bound approval" is defined
in exactly one place and exercised by the tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import GENESIS_HASH, canonical, chain_hash
from .models import Approval, AuditLog, Proposal, StandingRule
from .schemas import DecisionType, ProposalPayload


def _now() -> datetime:
    return datetime.now(timezone.utc)


def payload_hash(payload: dict) -> str:
    """Stable hash of a proposal payload, used to bind approvals to actions."""
    import hashlib

    return hashlib.sha256(canonical(payload).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Audit trail (append-only, hash-chained)
# --------------------------------------------------------------------------- #
def append_audit(
    session: Session,
    *,
    event_type: str,
    actor: str,
    payload: dict,
    proposal_id: str | None = None,
    approval_id: str | None = None,
) -> AuditLog:
    """Append one tamper-evident row, chaining off the previous row's hash."""
    last = session.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = last.this_hash if last else GENESIS_HASH

    # The hashed payload includes the linkage fields so they cannot be swapped
    # after the fact without breaking the chain.
    hashed = {
        "event_type": event_type,
        "actor": actor,
        "proposal_id": proposal_id,
        "approval_id": approval_id,
        "payload": payload,
    }
    this_hash = chain_hash(prev_hash, hashed)

    row = AuditLog(
        event_type=event_type,
        actor=actor,
        proposal_id=proposal_id,
        approval_id=approval_id,
        payload=payload,
        prev_hash=prev_hash,
        this_hash=this_hash,
    )
    session.add(row)
    session.flush()
    return row


# --------------------------------------------------------------------------- #
# Proposals
# --------------------------------------------------------------------------- #
def create_proposal(
    session: Session,
    *,
    payload: ProposalPayload,
    requested_by: str,
    slack_channel: str | None = None,
) -> Proposal:
    raw = payload.model_dump(mode="json")
    ph = payload_hash(raw)
    proposal = Proposal(
        repo=payload.repo,
        requested_by=requested_by,
        payload=raw,
        payload_hash=ph,
        status="proposed",
        slack_channel=slack_channel,
    )
    session.add(proposal)
    session.flush()
    append_audit(
        session,
        event_type="proposal.created",
        actor=requested_by,
        proposal_id=proposal.id,
        payload={
            "repo": payload.repo,
            "summary": payload.summary_line(),
            "counts": payload.counts(),
            "payload_hash": ph,
        },
    )
    return proposal


def get_proposal(session: Session, proposal_id: str) -> Proposal | None:
    return session.get(Proposal, proposal_id)


# --------------------------------------------------------------------------- #
# Approvals / decisions
# --------------------------------------------------------------------------- #
def record_decision(
    session: Session,
    *,
    proposal_id: str,
    approver: str,
    decision: DecisionType,
    time_limit_minutes: int | None = None,
) -> Approval | None:
    """Record a human decision. Returns the Approval (with a fresh
    ``approval_token``) for approving decisions, or ``None`` for a deny."""
    proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise ValueError(f"unknown proposal {proposal_id}")

    if decision == "deny":
        proposal.status = "denied"
        append_audit(
            session,
            event_type="proposal.denied",
            actor=approver,
            proposal_id=proposal_id,
            payload={"decision": decision},
        )
        return None

    expires_at = None
    if decision == "approve" and time_limit_minutes:
        expires_at = _now() + timedelta(minutes=time_limit_minutes)

    approval = Approval(
        proposal_id=proposal_id,
        approver=approver,
        decision=decision,
        approval_token=uuid.uuid4().hex,
        payload_hash=proposal.payload_hash,
        expires_at=expires_at,
    )
    session.add(approval)
    proposal.status = "approved"
    session.flush()

    # A "standing rule" decision also lays down a reusable pre-authorisation so
    # future proposals of the same shape don't need a human. (See
    # find_standing_approval.)
    if decision == "standing_rule":
        session.add(
            StandingRule(
                repo=proposal.repo,
                action_type="*",
                created_by=approver,
                active=True,
            )
        )

    append_audit(
        session,
        event_type="proposal.approved",
        actor=approver,
        proposal_id=proposal_id,
        approval_id=approval.id,
        payload={
            "decision": decision,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    return approval


def get_approval_by_token(session: Session, token: str) -> Approval | None:
    return session.execute(
        select(Approval).where(Approval.approval_token == token)
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Standing rules
# --------------------------------------------------------------------------- #
def find_standing_approval(
    session: Session, proposal: Proposal
) -> Approval | None:
    """If an active standing rule covers this whole proposal, mint an approval
    automatically (approver = 'standing-rule'). This is how a 'standing'
    permission removes the human from the loop for pre-blessed work — while
    still leaving a full audit record of *which* rule authorised it."""
    rules = session.execute(
        select(StandingRule).where(
            StandingRule.repo == proposal.repo, StandingRule.active.is_(True)
        )
    ).scalars().all()
    if not rules:
        return None

    covered_types = {r.action_type for r in rules}
    action_types = {a["type"] for a in proposal.payload.get("actions", [])}
    if "*" not in covered_types and not action_types.issubset(covered_types):
        return None

    approval = Approval(
        proposal_id=proposal.id,
        approver="standing-rule",
        decision="approve",
        approval_token=uuid.uuid4().hex,
        payload_hash=proposal.payload_hash,
    )
    session.add(approval)
    proposal.status = "approved"
    session.flush()
    append_audit(
        session,
        event_type="proposal.auto_approved",
        actor="standing-rule",
        proposal_id=proposal.id,
        approval_id=approval.id,
        payload={"rule_repo": proposal.repo},
    )
    return approval


# --------------------------------------------------------------------------- #
# The execution gate — the single source of truth the runner trusts
# --------------------------------------------------------------------------- #
class ApprovalError(Exception):
    """Raised when a request to execute is not backed by a valid approval."""


def validate_for_execution(
    session: Session, *, proposal_id: str, approval_token: str
) -> tuple[Proposal, Approval]:
    """Return ``(proposal, approval)`` only if execution is authorised.

    Every failure path raises :class:`ApprovalError` with a human-readable
    reason. The runner calls this and refuses (HTTP 403) on any exception. A
    compromised agent that lacks a valid token simply cannot get past here.
    """
    proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise ApprovalError("unknown proposal")

    approval = get_approval_by_token(session, approval_token)
    if approval is None:
        raise ApprovalError("no such approval token")
    if approval.proposal_id != proposal_id:
        raise ApprovalError("approval token does not match this proposal")
    if approval.decision == "deny":
        raise ApprovalError("proposal was denied")
    if approval.payload_hash != proposal.payload_hash:
        # Actions changed after approval — refuse. This blocks an agent from
        # getting a small batch approved and then swapping in new actions.
        raise ApprovalError("actions changed since approval (hash mismatch)")
    if proposal.status == "executed":
        raise ApprovalError("proposal already executed")
    if approval.expires_at is not None and _now() > _ensure_aware(approval.expires_at):
        raise ApprovalError("approval expired")
    if approval.decision == "approve_once" and approval.consumed_at is not None:
        raise ApprovalError("one-time approval already used")

    return proposal, approval


def _ensure_aware(dt: datetime) -> datetime:
    # SQLite round-trips naive datetimes; normalise to UTC-aware for comparison.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def mark_executed(
    session: Session,
    *,
    proposal: Proposal,
    approval: Approval,
    results: list[dict],
    actor: str,
) -> None:
    proposal.status = "executed"
    if approval.decision == "approve_once":
        approval.consumed_at = _now()
    append_audit(
        session,
        event_type="proposal.executed",
        actor=actor,
        proposal_id=proposal.id,
        approval_id=approval.id,
        payload={"results": results},
    )
