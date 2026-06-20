"""Read-only query helpers used by the dashboard API and the CLI."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import verify_chain
from .models import AuditLog, Proposal


def list_proposals(session: Session, limit: int = 100) -> list[dict]:
    rows = session.execute(
        select(Proposal).order_by(Proposal.created_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": p.id,
            "capability": p.capability,
            "subject": p.subject,
            "requested_by": p.requested_by,
            "status": p.status,
            "counts": _counts(p.payload),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]


def get_proposal_detail(session: Session, proposal_id: str) -> dict | None:
    p = session.get(Proposal, proposal_id)
    if p is None:
        return None
    return {
        "id": p.id,
        "capability": p.capability,
        "subject": p.subject,
        "requested_by": p.requested_by,
        "status": p.status,
        "payload": p.payload,
        "payload_hash": p.payload_hash,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def list_audit(session: Session, limit: int = 500) -> dict:
    rows = session.execute(
        select(AuditLog).order_by(AuditLog.seq.asc()).limit(limit)
    ).scalars().all()
    serial = [
        {
            "seq": r.seq,
            "event_type": r.event_type,
            "actor": r.actor,
            "proposal_id": r.proposal_id,
            "approval_id": r.approval_id,
            "payload": r.payload,
            "prev_hash": r.prev_hash,
            "this_hash": r.this_hash,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    # Recompute the hash chain so the dashboard can show "verified" / tampered.
    chain_rows = [
        {
            "seq": r.seq,
            "prev_hash": r.prev_hash,
            "this_hash": r.this_hash,
            "payload": {
                "event_type": r.event_type,
                "actor": r.actor,
                "proposal_id": r.proposal_id,
                "approval_id": r.approval_id,
                "payload": r.payload,
            },
        }
        for r in rows
    ]
    ok, bad = verify_chain(chain_rows)
    return {"entries": serial, "chain_ok": ok, "first_bad_seq": bad}


def _counts(payload: dict) -> dict[str, int]:
    """Count actions by type — capability-agnostic."""
    out: dict[str, int] = {}
    for a in payload.get("actions", []):
        out[a["type"]] = out.get(a["type"], 0) + 1
    return out
