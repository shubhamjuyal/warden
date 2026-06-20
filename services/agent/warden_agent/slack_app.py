"""Slack Bolt app (Socket Mode) — Warden's native surface.

Two interactions:

1. ``@warden triage owner/repo`` → run the LangGraph flow, persist a proposal in
   the ledger, and post the approval card.
2. Button clicks (Approve / Approve once / Deny / Standing rule) → record the
   human decision in the ledger and, for approvals, ask the runner to execute.

The approval *happens in Slack* — not a side web app — because that is where the
team already works. Slack is the legible "stop".
"""
from __future__ import annotations

import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from warden_common import ledger
from warden_common.config import agent_settings
from warden_common.db import init_engine, session_scope
from warden_common.schemas import ProposalPayload

from .deps import build_classifier, build_reader, build_runner_client
from .graph import run_triage
from .guards import assert_sandboxed
from .proposals import proposal_blocks

REPO_RE = re.compile(r"([\w.-]+/[\w.-]+)")

DECISION_LABELS = {
    "approve": "approved",
    "approve_once": "approved (one-time)",
    "deny": "denied",
    "standing_rule": "approved (standing rule)",
}


def build_app() -> App:
    s = agent_settings()
    app = App(token=s.slack_bot_token)

    @app.event("app_mention")
    def handle_mention(event, say):  # noqa: ANN001
        text = event.get("text", "")
        user = event.get("user", "unknown")
        channel = event.get("channel")
        if "triage" not in text:
            say("Try: `@warden triage owner/repo`")
            return
        match = REPO_RE.search(text.split("triage", 1)[1])
        if not match:
            say("I couldn't find a `owner/repo` in that. Try `@warden triage acme/api`.")
            return
        repo = match.group(1)
        say(f":hourglass_flowing_sand: Triaging open issues in `{repo}`…")
        _run_and_post(repo=repo, user=user, channel=channel, say=say)

    @app.action(re.compile(r"decision_(approve|approve_once|deny|standing_rule)"))
    def handle_decision(ack, body, action, say):  # noqa: ANN001
        ack()
        decision = action["action_id"].removeprefix("decision_")
        proposal_id = action["value"]
        approver = body["user"]["id"]
        _apply_decision(decision, proposal_id, approver, say)

    return app


def _run_and_post(*, repo: str, user: str, channel: str, say) -> None:  # noqa: ANN001
    reader = build_reader()
    classifier = build_classifier()
    try:
        payload: ProposalPayload = run_triage(
            reader, classifier, repo=repo, requested_by=user
        )
    finally:
        reader.close()

    if not payload.actions:
        say(f"No actions to propose for `{repo}` — everything looks triaged. :white_check_mark:")
        return

    with session_scope() as session:
        proposal = ledger.create_proposal(
            session, payload=payload, requested_by=user, slack_channel=channel
        )
        proposal_id = proposal.id

    say(blocks=proposal_blocks(proposal_id, payload), text="Warden triage proposal")


def _apply_decision(decision: str, proposal_id: str, approver: str, say) -> None:  # noqa: ANN001
    with session_scope() as session:
        approval = ledger.record_decision(
            session, proposal_id=proposal_id, approver=approver, decision=decision
        )
        token = approval.approval_token if approval else None

    if decision == "deny":
        say(f":no_entry: Proposal `{proposal_id[:8]}` denied by <@{approver}>. Nothing was executed.")
        return

    # Approved → ask the runner to execute. The agent itself still cannot write.
    runner = build_runner_client()
    try:
        result = runner.execute(proposal_id, token)
    except PermissionError as exc:
        say(f":lock: Runner refused execution: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        say(f":warning: Runner error: {exc}")
        return

    ok = result.get("ok")
    n = len(result.get("executed", []))
    status = ":white_check_mark:" if ok else ":warning:"
    say(
        f"{status} {DECISION_LABELS[decision]} by <@{approver}> — runner executed "
        f"{n} actions for proposal `{proposal_id[:8]}`. Full record in the audit dashboard."
    )


def main() -> None:
    # Refuse to start if a write credential leaked into the agent's env.
    assert_sandboxed()
    init_engine(create_all=True)
    s = agent_settings()
    app = build_app()
    SocketModeHandler(app, s.slack_app_token).start()


if __name__ == "__main__":
    main()
