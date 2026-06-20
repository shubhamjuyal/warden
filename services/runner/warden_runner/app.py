"""The permissioned runner service.

One meaningful endpoint: ``POST /execute``. It accepts only identifiers
(proposal id + approval token) — never an action list and never a credential.
It re-reads the authoritative proposal and approval from the ledger, runs the
gate (:func:`warden_common.ledger.validate_for_execution`), and refuses with
HTTP 403 on any failure. Only after the gate passes does it dispatch each action
to the executor registry — so it stays capability-agnostic.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from warden_common import ledger
from warden_common.config import runner_settings
from warden_common.db import init_engine, session_scope
from warden_common.ledger import ApprovalError
from warden_common.schemas import ExecuteRequest, ExecuteResponse, ProposalPayload

from .executors import Registry, Writer, build_default_registry, execute_proposal
from .github_write import GitHubWriteClient

# Built lazily on first use so the service can boot (and tests can run) without
# a live token; constructing the GitHub writer requires the write token.
_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        writer = GitHubWriteClient(runner_settings().github_write_token)
        _registry = build_default_registry(writer)
    return _registry


def set_writer(writer: Writer | None) -> None:
    """Test seam: rebuild the registry around an injected writer (or reset)."""
    global _registry
    _registry = build_default_registry(writer) if writer is not None else None


def set_registry(registry: Registry | None) -> None:
    """Test seam: inject a fully-formed registry (or reset to None)."""
    global _registry
    _registry = registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(create_all=True)
    yield


app = FastAPI(title="Warden Runner", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "warden-runner"}


@app.post("/execute", response_model=ExecuteResponse)
def execute(req: ExecuteRequest) -> ExecuteResponse:
    refusal: str | None = None
    response: ExecuteResponse | None = None

    # We do NOT raise inside the transaction — that would roll back the refusal
    # audit row we want to keep. Instead we record the outcome, let the scope
    # commit, then translate a refusal into a 403 afterwards.
    with session_scope() as session:
        try:
            proposal, approval = ledger.validate_for_execution(
                session,
                proposal_id=req.proposal_id,
                approval_token=req.approval_token,
            )
        except ApprovalError as exc:
            # A blocked attempt is part of the audit story — record it.
            ledger.append_audit(
                session,
                event_type="execute.refused",
                actor="runner",
                proposal_id=req.proposal_id,
                payload={"reason": str(exc)},
            )
            refusal = str(exc)
        else:
            # Execute exactly the actions recorded in the ledger, then record
            # the outcome on the immutable trail.
            payload = ProposalPayload.model_validate(proposal.payload)
            results = execute_proposal(payload, get_registry())
            ledger.mark_executed(
                session,
                proposal=proposal,
                approval=approval,
                results=[r.model_dump(mode="json") for r in results],
                actor="runner",
            )
            response = ExecuteResponse(
                proposal_id=proposal.id,
                executed=results,
                ok=all(r.ok for r in results),
            )

    if refusal is not None:
        raise HTTPException(status_code=403, detail=refusal)
    assert response is not None
    return response
