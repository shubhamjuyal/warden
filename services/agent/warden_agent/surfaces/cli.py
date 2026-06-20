"""Headless CLI over the same core the Slack app uses.

Subcommands are generated from the capability registry, so every capability is
runnable as ``warden <capability> <subject>`` (e.g. ``warden triage acme/api``)
with no per-capability CLI code. Plus ledger inspection:

    warden <capability> <subject>   run a capability, persist a proposal, print it
    warden approve <proposal_id>    record approval + ask the runner to execute
    warden deny <proposal_id>       record a denial
    warden proposals                list recent proposals
    warden audit                    print the hash-chained audit trail + verify
"""
from __future__ import annotations

import argparse
import json
import sys

from warden_common import ledger, reads
from warden_common.db import init_engine, session_scope

from .. import capabilities
from ..deps import build_runner_client
from ..guards import assert_sandboxed


def _cmd_capability(args: argparse.Namespace) -> int:
    capability = capabilities.get(args.cmd)
    assert capability is not None
    payload = capability.run(subject=args.subject, requested_by=args.user)
    if not payload.actions:
        print(f"No actions to propose for {args.subject}.")
        return 0
    with session_scope() as session:
        proposal = ledger.create_proposal(
            session, payload=payload, requested_by=args.user
        )
        pid = proposal.id
    print(f"[{capability.name}] {capability.summarize(payload)}")
    print(f"proposal_id = {pid}")
    print(f"Approve with:  warden approve {pid}")
    return 0


def _cmd_decide(args: argparse.Namespace, decision: str) -> int:
    with session_scope() as session:
        approval = ledger.record_decision(
            session, proposal_id=args.proposal_id, approver=args.user, decision=decision
        )
        token = approval.approval_token if approval else None
    if decision == "deny":
        print(f"Denied {args.proposal_id}. Nothing executed.")
        return 0
    try:
        result = build_runner_client().execute(args.proposal_id, token)
    except PermissionError as exc:
        print(f"Runner refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_proposals(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        for p in reads.list_proposals(session):
            print(
                f"{p['id']}  {p['status']:10}  {p['capability']:12}  "
                f"{p['subject']:24}  {p['counts']}"
            )
    return 0


def _cmd_audit(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        data = reads.list_audit(session)
    for e in data["entries"]:
        print(f"#{e['seq']:>3} {e['event_type']:22} {e['actor']:16} {e['this_hash'][:12]}")
    print("-" * 60)
    print(
        "chain_ok =",
        data["chain_ok"],
        "" if data["chain_ok"] else f"(broken at {data['first_bad_seq']})",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="warden")
    parser.add_argument("--user", default="cli-user", help="actor name for the ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # One subcommand per registered capability.
    for cap in capabilities.all_capabilities():
        c = sub.add_parser(cap.name, help=cap.help)
        c.add_argument("subject", help="what to run against, e.g. owner/repo")
        c.set_defaults(func=_cmd_capability)

    for name in ("approve", "approve_once", "deny"):
        d = sub.add_parser(name)
        d.add_argument("proposal_id")
        d.set_defaults(func=lambda a, _n=name: _cmd_decide(a, _n))

    sub.add_parser("proposals").set_defaults(func=_cmd_proposals)
    sub.add_parser("audit").set_defaults(func=_cmd_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    assert_sandboxed()
    init_engine(create_all=True)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
