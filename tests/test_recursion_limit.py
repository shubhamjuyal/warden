"""Hitting the step limit yields a clean reply, not a raw LangGraph error.

If the agent loops past its recursion limit, ``run_turn`` must catch it and
return a friendly message — never surface LangGraph's internals (which include a
docs URL Slack would unfurl). We force the limit by scripting a model that always
calls a tool and setting the limit very low.
"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import warden_agent.brain.agent as agent_mod
import warden_agent.capabilities.explorer.tools as explorer_tools
from warden_agent.brain import SlackTurnContext, build_agent, run_turn

from .fakes import FakeRepoReader


class LoopingChatModel(BaseChatModel):
    """Always calls a read tool — never emits a final answer, so it loops."""

    def bind_tools(self, tools, **kwargs) -> "LoopingChatModel":  # noqa: ANN001
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # noqa: ANN001
        msg = AIMessage(
            content="",
            tool_calls=[{
                "name": "list_branches",
                "args": {"repo": "acme/api"},
                "id": f"call_{len(messages)}",
                "type": "tool_call",
            }],
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "looping"


def test_recursion_limit_yields_friendly_reply(ledger_db, monkeypatch):
    monkeypatch.setattr(explorer_tools, "build_repo_reader", lambda: FakeRepoReader())

    class _Settings:
        agent_recursion_limit = 3

    monkeypatch.setattr(agent_mod, "agent_settings", lambda: _Settings())

    agent = build_agent(LoopingChatModel())
    ctx = SlackTurnContext(user="U1", channel="C1", thread_ts="t", say=lambda **k: None)

    reply = run_turn("go", ctx, agent=agent)

    assert "more steps" in reply.lower()
    assert "http" not in reply.lower()  # no unfurlable URL / raw error
