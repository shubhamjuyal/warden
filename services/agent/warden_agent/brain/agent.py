"""The brain: one LangGraph tool-calling agent for the whole bot.

There is exactly one agent. It receives a user's Slack message, reasons about
intent, and either asks a clarifying question or calls a capability tool (via the
model's native function-calling — never string matching). A ``MemorySaver``
checkpointer keyed on the Slack thread gives it coherent multi-turn memory, so a
clarification and its answer belong to the same conversation.

Slack is pure I/O around this: the surface feeds messages in and posts replies
out. All routing and conversation lives here.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent

from warden_common.config import agent_settings

from .context import SlackTurnContext, reset_turn, set_turn
from .tools import build_tools

SYSTEM_PROMPT = """You are Warden, an AI engineering teammate that lives in Slack.

You help the team by running capabilities (your tools) on their behalf. Each tool
reasons read-only and proposes consequential actions; a human always approves them
in Slack before anything happens — you never take an action directly.

How to behave:
- Figure out what the user wants and pick the right tool. Don't require exact
  command phrasing — "can you triage the issues on acme/payments?" should map to
  the triage tool with subject "acme/payments".
- If a required argument is missing or ambiguous (e.g. the user says "triage the
  issues" without naming a repo), ASK one short clarifying question instead of
  calling a tool or guessing. Use the conversation so far — if the repo was given
  earlier in the thread, reuse it.
- After you call a tool, it posts an approval card in the thread. Briefly tell the
  user what you proposed and that they need to Approve or Deny it.
- If you can't help with something, say so plainly and mention what you can do.
- Be concise, friendly, and conversational. You're talking in a Slack thread."""


def _default_llm():
    """The single chat model behind the agent (OpenAI gpt-4o by default)."""
    from langchain_openai import ChatOpenAI

    s = agent_settings()
    if not s.openai_api_key:
        raise RuntimeError(
            "The Warden brain requires OPENAI_API_KEY. Set it, or inject a model "
            "via build_agent() for offline runs/tests."
        )
    return ChatOpenAI(model=s.openai_model, api_key=s.openai_api_key, temperature=0)


def build_agent(llm) -> CompiledGraph:  # noqa: ANN001 - any LangChain chat model
    """Compile a react agent over the current capability tools. Injectable LLM so
    tests can drive it without a live OpenAI key."""
    return create_react_agent(
        llm,
        build_tools(),
        prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


@lru_cache
def get_agent() -> CompiledGraph:
    """The one agent instance for the running bot."""
    return build_agent(_default_llm())


def _final_text(result: dict) -> str:
    messages = result.get("messages", [])
    if not messages:  # pragma: no cover - create_react_agent always returns messages
        return ""
    content = messages[-1].content
    if isinstance(content, list):  # some models return content blocks
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        ).strip()
    return str(content).strip()


def run_turn(text: str, ctx: SlackTurnContext, *, agent: CompiledGraph | None = None) -> str:
    """Run one conversational turn and return the agent's reply text.

    ``ctx`` carries the Slack runtime context tools need; it is bound for the
    duration of the turn. The thread id (``channel:thread_ts``) selects the
    checkpointer memory so the thread stays coherent across turns.
    """
    agent = agent or get_agent()
    token = set_turn(ctx)
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": f"{ctx.channel}:{ctx.thread_ts}"}},
        )
    finally:
        reset_turn(token)
    return _final_text(result)
