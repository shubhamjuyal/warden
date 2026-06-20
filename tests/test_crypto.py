"""The hash chain is the backbone of the immutable audit trail."""
from warden_common.crypto import GENESIS_HASH, chain_hash, verify_chain


def _make_chain(payloads):
    rows, prev = [], GENESIS_HASH
    for i, p in enumerate(payloads, start=1):
        h = chain_hash(prev, p)
        rows.append({"seq": i, "prev_hash": prev, "this_hash": h, "payload": p})
        prev = h
    return rows


def test_intact_chain_verifies():
    rows = _make_chain([{"a": 1}, {"a": 2}, {"a": 3}])
    ok, bad = verify_chain(rows)
    assert ok is True
    assert bad is None


def test_tampering_with_a_row_breaks_the_chain():
    rows = _make_chain([{"a": 1}, {"a": 2}, {"a": 3}])
    # Someone edits the payload of row 2 after the fact, but can't recompute the
    # downstream hashes without the chain.
    rows[1]["payload"] = {"a": 999}
    ok, bad = verify_chain(rows)
    assert ok is False
    assert bad == 2


def test_deleting_a_row_breaks_linkage():
    rows = _make_chain([{"a": 1}, {"a": 2}, {"a": 3}])
    del rows[1]  # remove the middle row
    ok, bad = verify_chain(rows)
    assert ok is False
    assert bad == 3  # row 3's prev_hash no longer matches row 1's this_hash
