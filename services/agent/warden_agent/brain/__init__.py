"""Warden's brain: the single conversational agent behind the Slack bot.

The Slack surface calls :func:`run_turn` with the user's message and a
:class:`SlackTurnContext`; the agent reasons about intent, calls capability tools,
and returns a reply to post in-thread.
"""
from __future__ import annotations

from .agent import build_agent, get_agent, run_turn
from .context import SlackTurnContext

__all__ = ["run_turn", "get_agent", "build_agent", "SlackTurnContext"]
