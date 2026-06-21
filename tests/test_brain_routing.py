"""The conversational brain routes natural language to the right tool — or asks.

These tests drive the single agent with a *scripted* chat model (no OpenAI key,
no network) so we can assert the two behaviours that matter:

  1. A natural-language request that names a repo -> the agent calls the triage
     tool, which persists a proposal and posts an approval card in the thread.
  2. A request with no repo -> the agent asks a clarifying question and proposes
     nothing.

Tool selection here is real LangGraph function-calling; only the model's token
output is scripted. Triage's GitHub reader and OpenAI classifier are swapped for
the existing fakes so the capability runs fully offline.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

import warden_agent.capabilities.triage as triage_mod
from warden_agent.brain import SlackTurnContext, build_agent, run_turn
from warden_common import reads
from warden_common.db import session_scope

from .fakes import SAMPLE_CLASSIFICATIONS, SAMPLE_ISSUES, FakeClassifier, FakeReader


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns pre-baked AIMessages in order — enough for
    create_react_agent's loop (a tool call, then a final reply)."""

    responses: list[AIMessage]
    _idx: int = PrivateAttr(default=0)

    def bind_tools(self, tools, **kwargs) -> "ScriptedChatModel":  # noqa: ANN001
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # noqa: ANN001
        msg = self.responses[self._idx]
        self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "scripted"


class RecordingSay:
    """Stands in for Slack Bolt's ``say`` — records what would be posted."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.fixture()
def offline_triage(monkeypatch):
    """Run the triage capability without GitHub or OpenAI."""
    monkeypatch.setattr(triage_mod, "build_reader", lambda: FakeReader(SAMPLE_ISSUES))
    monkeypatch.setattr(
        triage_mod, "build_classifier", lambda: FakeClassifier(SAMPLE_CLASSIFICATIONS)
    )


def _ctx(say: RecordingSay) -> SlackTurnContext:
    return SlackTurnContext(user="U1", channel="C1", thread_ts="1111.0001", say=say)


def test_natural_language_routes_to_triage_and_proposes(ledger_db, offline_triage):
    # The model decides to call the triage tool with the repo it extracted, then
    # replies in words.
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "triage",
                        "args": {"subject": "acme/api"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="I've proposed triage for acme/api — please Approve or Deny."),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn("can you triage the issues on acme/api?", _ctx(say), agent=agent)

    # A proposal was persisted...
    with session_scope() as s:
        proposals = reads.list_proposals(s)
    assert len(proposals) == 1
    assert proposals[0]["capability"] == "triage"
    assert proposals[0]["subject"] == "acme/api"

    # ...and an approval card was posted into the thread.
    card_posts = [c for c in say.calls if "blocks" in c]
    assert len(card_posts) == 1
    assert card_posts[0]["thread_ts"] == "1111.0001"

    assert "acme/api" in reply


def test_missing_repo_asks_instead_of_acting(ledger_db, offline_triage):
    # No repo named -> the model asks rather than calling a tool.
    model = ScriptedChatModel(
        responses=[AIMessage(content="Sure — which repository should I triage?")]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn("hey warden, can you triage the issues?", _ctx(say), agent=agent)

    assert "which repository" in reply.lower()
    with session_scope() as s:
        assert reads.list_proposals(s) == []
    assert say.calls == []  # nothing posted, nothing proposed
