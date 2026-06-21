"""Slack Bolt app (Socket Mode) — Warden's native surface.

Slack is pure I/O here. A single conversational agent (``warden_agent.brain``) is
the brain: it reads the user's message, decides which capability to run (via the
model's function-calling, not string matching), asks clarifying questions when a
request is ambiguous, and replies in-thread. This surface only:

  * feeds inbound messages to the agent (mentions, and follow-up thread replies),
  * posts the agent's reply back into the thread, and
  * handles the approval-card buttons, which remain the legible human "stop":
    Approve / Approve once / Deny / Standing rule still record the decision and,
    for approvals, ask the runner to execute. The agent itself never writes.

Conversation:
  * An @mention starts (or continues) a thread. Warden remembers the thread.
  * Once a thread is active, plain replies in it are handled too — no re-mention
    needed — so the back-and-forth feels natural.

Shipping a new capability requires no changes here: tools are derived from the
capability registry, so a newly registered capability simply becomes callable.
"""
from __future__ import annotations

import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from warden_common import ledger
from warden_common.config import agent_settings
from warden_common.db import init_engine, session_scope

from .. import brain
from ..deps import build_runner_client
from ..guards import assert_sandboxed

DECISION_LABELS = {
    "approve": "approved",
    "approve_once": "approved (one-time)",
    "deny": "denied",
    "standing_rule": "approved (standing rule)",
}

# Threads Warden is taking part in. Once it's been mentioned in a thread, we also
# pick up plain (unmentioned) replies there. In-process and best-effort — losing
# it on restart just means the user @mentions again to resume.
_active_threads: set[str] = set()


def build_app() -> App:
    s = agent_settings()
    app = App(token=s.slack_bot_token)
    bot_user_id = app.client.auth_test().get("user_id")

    @app.event("app_mention")
    def handle_mention(event, say):  # noqa: ANN001
        thread_ts = event.get("thread_ts") or event.get("ts")
        _active_threads.add(thread_ts)
        _handle_user_turn(event, say, thread_ts)

    @app.event("message")
    def handle_message(event, say):  # noqa: ANN001
        # Only follow-up replies in a thread Warden is already part of. Everything
        # else (channel chatter, our own messages, mentions) is ignored here.
        if event.get("bot_id") or event.get("subtype"):
            return  # our own / non-user messages — never loop on these
        if event.get("user") == bot_user_id:
            return
        thread_ts = event.get("thread_ts")
        if not thread_ts or thread_ts not in _active_threads:
            return
        if bot_user_id and f"<@{bot_user_id}>" in event.get("text", ""):
            return  # a mention — handled by app_mention, don't double-process
        _handle_user_turn(event, say, thread_ts)

    @app.action(re.compile(r"decision_(approve|approve_once|deny|standing_rule)"))
    def handle_decision(ack, body, action, say):  # noqa: ANN001
        ack()
        decision = action["action_id"].removeprefix("decision_")
        proposal_id = action["value"]
        approver = body["user"]["id"]
        message = body.get("message") or {}
        thread_ts = message.get("thread_ts") or message.get("ts")
        _apply_decision(decision, proposal_id, approver, say, thread_ts)

    return app


def _handle_user_turn(event, say, thread_ts: str) -> None:  # noqa: ANN001
    """One inbound message -> agent -> reply, all in the same thread."""
    text = event.get("text", "")
    user = event.get("user", "unknown")
    channel = event.get("channel")

    ctx = brain.SlackTurnContext(
        user=user, channel=channel, thread_ts=thread_ts, say=say
    )
    try:
        reply = brain.run_turn(text, ctx)
    except Exception as exc:  # noqa: BLE001 - surface errors to the user, don't crash the socket
        say(text=f":warning: Something went wrong: {exc}", thread_ts=thread_ts)
        return
    if reply:
        say(text=reply, thread_ts=thread_ts)


def _apply_decision(  # noqa: ANN001
    decision: str, proposal_id: str, approver: str, say, thread_ts: str | None = None
) -> None:
    with session_scope() as session:
        approval = ledger.record_decision(
            session, proposal_id=proposal_id, approver=approver, decision=decision
        )
        token = approval.approval_token if approval else None

    if decision == "deny":
        say(
            text=f":no_entry: Proposal `{proposal_id[:8]}` denied by <@{approver}>. Nothing was executed.",
            thread_ts=thread_ts,
        )
        return

    # Approved → ask the runner to execute. The agent itself still cannot write.
    runner = build_runner_client()
    try:
        result = runner.execute(proposal_id, token)
    except PermissionError as exc:
        say(text=f":lock: Runner refused execution: {exc}", thread_ts=thread_ts)
        return
    except Exception as exc:  # noqa: BLE001
        say(text=f":warning: Runner error: {exc}", thread_ts=thread_ts)
        return

    ok = result.get("ok")
    n = len(result.get("executed", []))
    status = ":white_check_mark:" if ok else ":warning:"
    say(
        text=(
            f"{status} {DECISION_LABELS[decision]} by <@{approver}> — runner executed "
            f"{n} actions for proposal `{proposal_id[:8]}`. Full record in the audit dashboard."
        ),
        thread_ts=thread_ts,
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
