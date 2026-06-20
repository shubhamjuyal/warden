"""Hash-chain primitives for the append-only audit trail.

Each audit row stores the hash of the previous row. ``this_hash`` is derived
from ``prev_hash`` plus a canonical serialisation of the row's payload, so any
tampering with an earlier row breaks every hash after it. This gives the audit
trail its tamper-evidence: it is not a verbose log dump, but a record a human
can trust to reconstruct what happened.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def canonical(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, stable across runs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def chain_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """Hash a row given the previous row's hash and this row's payload."""
    material = f"{prev_hash}\n{canonical(payload)}".encode()
    return hashlib.sha256(material).hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Recompute the chain over ``rows`` (ordered by seq).

    Returns ``(ok, first_bad_seq)``. ``first_bad_seq`` is the seq of the first
    row whose stored hash does not match the recomputed value, or ``None`` when
    the chain is intact.
    """
    prev = GENESIS_HASH
    for row in rows:
        expected = chain_hash(prev, row["payload"])
        if expected != row["this_hash"] or row["prev_hash"] != prev:
            return False, row["seq"]
        prev = row["this_hash"]
    return True, None
