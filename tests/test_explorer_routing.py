"""The brain routes repo questions to read-only tools — and proposes nothing.

Same setup as ``test_brain_routing``: a scripted chat model drives real LangGraph
function-calling, with the explorer's GitHub reader swapped for a fake so it runs
offline. The point of these tests is the negative space: a read tool answers in
the thread, persists NO proposal, and posts NO approval card. That's the proof
the read path sidesteps the propose→approve→runner flow entirely.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

import warden_agent.capabilities.explorer.tools as explorer_tools
from warden_agent.brain import SlackTurnContext, build_agent, run_turn
from warden_common import reads
from warden_common.db import session_scope

from .fakes import FakeRepoReader


class ScriptedChatModel(BaseChatModel):
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
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.fixture()
def offline_explorer(monkeypatch):
    """Run the explorer tools without GitHub."""
    monkeypatch.setattr(
        explorer_tools,
        "build_repo_reader",
        lambda: FakeRepoReader({"README.md": "# Acme API\nthe canonical readme"}),
    )


def _ctx(say: RecordingSay) -> SlackTurnContext:
    return SlackTurnContext(user="U1", channel="C1", thread_ts="2222.0002", say=say)


def test_read_file_answers_without_proposing(ledger_db, offline_explorer):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"repo": "acme/api", "path": "README.md"},
                    "id": "call_1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Here's the README: the canonical readme"),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn("show me the README of acme/api", _ctx(say), agent=agent)

    # Nothing was proposed and no approval card was posted — it just answered.
    with session_scope() as s:
        assert reads.list_proposals(s) == []
    assert say.calls == []
    assert "canonical readme" in reply


def test_how_many_issues_routes_to_list_issues_not_triage(ledger_db, offline_explorer):
    # The case from the screenshot: a plain "how many issues" question must be
    # answered by reading, never by offering triage (which would propose changes).
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "list_issues",
                    "args": {"repo": "acme/api", "state": "open"},
                    "id": "call_1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="acme/api has 2 open issues."),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn('how many issues in "acme/api"?', _ctx(say), agent=agent)

    with session_scope() as s:
        assert reads.list_proposals(s) == []  # nothing proposed
    assert say.calls == []  # no approval card
    assert "2" in reply


def test_list_branches_routes_to_read_tool(ledger_db, offline_explorer):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "list_branches",
                    "args": {"repo": "acme/api"},
                    "id": "call_1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="acme/api has these branches: main, dev"),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn("what branches does acme/api have?", _ctx(say), agent=agent)

    with session_scope() as s:
        assert reads.list_proposals(s) == []
    assert say.calls == []
    assert "main" in reply
