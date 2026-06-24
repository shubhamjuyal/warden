"""Per-turn Slack context for the conversational agent.

The brain's tools need to know *who* is asking and *where* to post the approval
card (Slack user, channel, thread). That runtime context is not something the LLM
should supply — the model only ever extracts the capability ``subject`` from the
user's words. So we stash it in a :class:`contextvars.ContextVar` for the duration
of one turn and let the tool implementations read it.

``contextvars`` (rather than a module global) keeps turns isolated even though
Slack Bolt dispatches events on a thread pool: each turn sets and resets its own
token.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any, Callable

from warden_common.schemas import Action


@dataclass
class SlackTurnContext:
    """Everything a tool needs about the Slack turn it runs inside."""

    user: str
    channel: str
    thread_ts: str
    #: Slack Bolt's ``say`` for this event — used to post the approval card.
    say: Callable[..., Any]
    #: Write actions staged this turn by the fixer tools (create_branch,
    #: commit_code, open_pr). ``submit_change`` bundles them into one proposal.
    #: Per-turn, so a fix is assembled within a single reasoning turn.
    staging: list[Action] = field(default_factory=list)
    #: The repo all staged actions belong to (the proposal's subject).
    staging_subject: str = ""


_CURRENT: contextvars.ContextVar[SlackTurnContext | None] = contextvars.ContextVar(
    "warden_slack_turn", default=None
)


def set_turn(ctx: SlackTurnContext) -> contextvars.Token:
    """Bind the context for this turn; pass the token to :func:`reset_turn`."""
    return _CURRENT.set(ctx)


def reset_turn(token: contextvars.Token) -> None:
    _CURRENT.reset(token)


def current_turn() -> SlackTurnContext:
    ctx = _CURRENT.get()
    if ctx is None:  # pragma: no cover - guards against tool use outside a turn
        raise RuntimeError(
            "No active Slack turn. A capability tool was invoked outside of "
            "brain.run_turn()."
        )
    return ctx
