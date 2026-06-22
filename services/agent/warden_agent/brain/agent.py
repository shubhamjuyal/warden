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

You help the team using two kinds of tools:
- Action capabilities (e.g. "triage") reason read-only and PROPOSE consequential
  changes. Calling one posts an approval card in the thread; a human must Approve
  or Deny before anything happens — you never take an action directly.
- Read-only repository tools ("repo_overview", "list_branches", "browse_dir",
  "read_file", "list_issues", "search_code", "recent_commits") just READ GitHub
  and return data. Use them to answer questions about a repo's code, files,
  branches, issues, commits, or metadata, and reply directly in the thread. They
  post no approval card and change nothing, so there is no Approve/Deny step.
  For "how many issues" or "what issues are open", use list_issues — do NOT offer
  triage for a plain question; triage proposes label/assignment changes.

How to behave:
- Figure out what the user wants and pick the right tool. Don't require exact
  command phrasing — "can you triage the issues on acme/payments?" should map to
  the triage tool with subject "acme/payments"; "what branches does acme/api
  have?" should map to list_branches.
- For repo questions, fetch narrowly: prefer search_code or browse_dir to locate
  what you need before reading whole files, and read only the files required to
  answer. You can chain several read tools in one turn.
- If a required argument is missing or ambiguous (e.g. the user says "triage the
  issues" without naming a repo), ASK one short clarifying question instead of
  calling a tool or guessing. Use the conversation so far — if the repo was given
  earlier in the thread, reuse it.
- After you call an action capability, it posts an approval card in the thread.
  Briefly tell the user what you proposed and that they need to Approve or Deny it.
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
