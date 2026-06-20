"""Thin client the agent uses to *ask* the runner to execute.

This is the full extent of the agent's "write" power: it can POST a proposal id
and an approval token to the runner. It cannot pass actions or credentials. If
the token isn't backed by a real human approval in the ledger, the runner says
403 and nothing happens.
"""
from __future__ import annotations

import httpx


class RunnerClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def execute(self, proposal_id: str, approval_token: str) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/execute",
                json={"proposal_id": proposal_id, "approval_token": approval_token},
            )
        if resp.status_code == 403:
            raise PermissionError(resp.json().get("detail", "refused by runner"))
        resp.raise_for_status()
        return resp.json()
