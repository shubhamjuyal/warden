"""The brain stages a fix across independent tools, then bundles ONE proposal.

Same scripted-model setup as the other brain tests. The point here: calling
create_branch, commit_code, and open_pr stages nothing visible — no proposal, no
card — until submit_change, which posts exactly one approval card whose proposal
holds the three actions in order (branch -> commit -> PR). Nothing is executed:
the agent only proposes; the runner would write after a human approves.
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from warden_agent.brain import SlackTurnContext, build_agent, run_turn
from warden_common import reads
from warden_common.db import session_scope


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


def _tool_call(name: str, args: dict, n: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{n}", "type": "tool_call"}])


def _ctx(say: RecordingSay) -> SlackTurnContext:
    return SlackTurnContext(user="U1", channel="C1", thread_ts="3333.0003", say=say)


def test_fix_stages_then_bundles_one_proposal(ledger_db):
    # The model drives the full fix: branch, commit, PR, then submit.
    model = ScriptedChatModel(
        responses=[
            _tool_call("create_branch", {"repo": "acme/api", "branch": "fix/login"}, 1),
            _tool_call("commit_code", {
                "repo": "acme/api", "branch": "fix/login", "path": "src/auth.py",
                "content": "fixed file body", "message": "fix NPE",
            }, 2),
            _tool_call("open_pr", {
                "repo": "acme/api", "head": "fix/login", "title": "Fix login NPE",
                "body": "Fixes #1",
            }, 3),
            _tool_call("submit_change", {}, 4),
            AIMessage(content="Posted an approval card for the fix to acme/api."),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    reply = run_turn("fix issue #1 in acme/api", _ctx(say), agent=agent)

    # Exactly one proposal, holding the three actions in dependency order.
    with session_scope() as s:
        proposals = reads.list_proposals(s)
        assert len(proposals) == 1
        full = reads.get_proposal_detail(s, proposals[0]["id"])
    assert proposals[0]["capability"] == "fixer"
    assert proposals[0]["subject"] == "acme/api"
    types = [a["type"] for a in full["payload"]["actions"]]
    assert types == ["create_branch", "commit_file", "open_pr"]

    # Exactly one approval card was posted (not one per staged step).
    cards = [c for c in say.calls if "blocks" in c]
    assert len(cards) == 1
    assert "approval card" in reply.lower()


def test_staging_without_submit_proposes_nothing(ledger_db):
    # Staging steps alone must not persist or post anything.
    model = ScriptedChatModel(
        responses=[
            _tool_call("create_branch", {"repo": "acme/api", "branch": "fix/login"}, 1),
            AIMessage(content="I staged a branch; tell me to continue."),
        ]
    )
    agent = build_agent(model)
    say = RecordingSay()

    run_turn("start a fix on acme/api", _ctx(say), agent=agent)

    with session_scope() as s:
        assert reads.list_proposals(s) == []
    assert say.calls == []  # nothing proposed, no card
