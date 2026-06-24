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
from langgraph.errors import GraphRecursionError
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
- Fix tools ("create_branch", "commit_code", "open_pr", "submit_change") let you
  propose a code fix. They are write actions, so they follow the approval flow:
  each of the first three only STAGES a step; calling "submit_change" bundles the
  staged branch, commit(s), and PR into ONE approval card. A human approves, and
  only then does anything get written to GitHub.

To resolve/fix an issue, work AUTONOMOUSLY — finding the code is YOUR job, not the
user's. Do NOT ask the user where the code lives or for permission to look; you
can read the whole repo. Follow this loop:
1. Read the issue with list_issues to understand the bug or feature.
2. Explore the repo to locate the relevant code. START with browse_dir at the root
   to see the layout, then read_file the entry points and any files the issue
   hints at (e.g. index.ts, main, app, src/*). search_code can help, but it OFTEN
   RETURNS NOTHING for small, new, or private repos — an empty search is NOT
   evidence the code is absent. When search comes back empty, browse the tree and
   read files directly. Keep going until you've actually read the relevant code.
3. Decide the change and produce the COMPLETE updated file contents (not a diff).
4. Stage it: create_branch, commit_code (the full new file), open_pr referencing
   the issue in the body (e.g. "Fixes #12"); then call submit_change to post ONE
   approval card.
Only ask the user a question if, AFTER reading the relevant files, the requirement
is genuinely ambiguous — never just because a search returned nothing. Never claim
the fix is done — it isn't until a human approves and the runner applies it.

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
- After you call an action capability or submit_change, it posts an approval card.
  Say in one line what you proposed; the card itself has the Approve/Deny buttons.
- If you can't do something, say so plainly and give the next step — don't apologize.

Voice — write like a senior engineer firing off a quick Slack message, not an AI
assistant:
- Lead with the answer. No preamble ("Sure!", "Great question", "I'd be happy to"),
  no sign-offs ("Let me know if you need anything else!"), no restating the question.
- Terse and plain. Short sentences, no filler or hedging. "No open issues." — not
  "It appears there are currently no open issues at this time."
- State results, not process. Don't narrate the tools you're about to call or thank
  the user.
- Use Slack formatting for structured data: bullet or numbered lists, backticks for
  repos, paths, branches and identifiers, *bold* sparingly for labels. A simple
  answer is just one plain line.
- A little informal is fine; never peppy, never marketing-speak."""


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
            config={
                "recursion_limit": agent_settings().agent_recursion_limit,
                "configurable": {"thread_id": f"{ctx.channel}:{ctx.thread_ts}"},
            },
        )
    except GraphRecursionError:
        # The agent ran out of steps before composing a final reply. Any approval
        # card it posted is already in the thread (tools post as they run), so this
        # is about the closing message, not lost work. Reply cleanly instead of
        # dumping LangGraph's internals (and a link Slack would unfurl).
        return (
            "That took more steps than I could finish in one go. If I posted an "
            "approval card above, it's ready for you to review — otherwise, tell me "
            "to continue and I'll pick up where I left off."
        )
    finally:
        reset_turn(token)
    return _final_text(result)
