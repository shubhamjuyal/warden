"""SQLAlchemy ORM models for the permission ledger.

Four tables:

* ``proposals``     — what the agent asked to do (immutable once created).
* ``approvals``     — a human's decision on a proposal (one-time / time-limited
                      / standing). Carries the unforgeable ``approval_token``.
* ``standing_rules``— pre-authorisations the runner can match future actions to.
* ``audit_log``     — append-only, hash-chained record of everything.

The audit_log is append-only at two layers: the ledger API never updates or
deletes rows, and (on Postgres) a trigger physically rejects UPDATE/DELETE.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Which capability produced this proposal (e.g. "triage"). Lets one ledger
    # serve many capabilities and lets the dashboard group by capability.
    capability: Mapped[str] = mapped_column(String(64), default="")
    # The scope the capability ran against (e.g. a repo "acme/api"). Generic on
    # purpose — different capabilities have different kinds of subject.
    subject: Mapped[str] = mapped_column(String(255))
    requested_by: Mapped[str] = mapped_column(String(255))  # slack user id/name
    # Frozen snapshot of ProposalPayload — the authoritative action list.
    payload: Mapped[dict] = mapped_column(JSON)
    # sha256 over the canonical payload; the approval binds to this hash so the
    # actions cannot change between proposal and execution.
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    slack_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slack_message_ts: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"))
    approver: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(32))  # DecisionType
    # The capability the runner checks. Random, unguessable, single proposal.
    approval_token: Mapped[str] = mapped_column(String(64), default=_uuid, index=True)
    # Binds the approval to the exact actions that were shown to the human.
    payload_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StandingRule(Base):
    __tablename__ = "standing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    subject: Mapped[str] = mapped_column(String(255))
    action_type: Mapped[str] = mapped_column(String(32))  # action type or "*"
    created_by: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    # Monotonic sequence — the order of the chain.
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(255))
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    this_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
