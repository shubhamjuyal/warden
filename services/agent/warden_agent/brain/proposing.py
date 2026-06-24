"""Posting proposals, and the fixer's write-proposing tools.

Two things live here:

1. :func:`post_proposal` — the shared tail every proposing path uses: persist the
   proposal in the ledger and post a Slack approval card in the thread. Both the
   capability tools (triage) and the fixer's ``submit_change`` reuse it, so there
   is exactly one place a proposal becomes an approval card.

2. The fixer's write tools. ``create_branch``, ``commit_code``, and ``open_pr``
   are independent, composable tools — but each only *stages* a write action onto
   the current turn; nothing is proposed or written when they're called.
   ``submit_change`` then bundles the staged actions into ONE proposal and posts a
   single approval card. A human approves, and only then does the runner perform
   the branch, commit, and PR — in order. The agent never writes to GitHub; this
   module imports no write client and never touches the runner.
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from warden_common import ledger
from warden_common.db import session_scope
from warden_common.schemas import ProposalPayload

from ..capabilities.fixer import actions as fixer
from ..surfaces.cards import proposal_blocks
from .context import current_turn


def post_proposal(payload: ProposalPayload, summary: str) -> str:
    """Persist ``payload`` and post an approval card into the Slack thread.

    Returns a short confirmation for the model to relay. Shared by every path
    that turns a ProposalPayload into a human approval.
    """
    ctx = current_turn()
    with session_scope() as session:
        proposal = ledger.create_proposal(
            session, payload=payload, requested_by=ctx.user, slack_channel=ctx.channel
        )
        proposal_id = proposal.id

    ctx.say(
        blocks=proposal_blocks(proposal_id, payload, summary),
        text="Warden proposal",
        thread_ts=ctx.thread_ts,
    )
    return (
        f"Posted an approval card for {payload.subject}: {summary} "
        f"(proposal {proposal_id[:8]}). Nothing runs until a human approves."
    )


# -- staging helpers ------------------------------------------------------- #
def _stage(action, subject: str) -> None:
    """Add an action to this turn's staging, recording its repo (subject)."""
    ctx = current_turn()
    ctx.staging_subject = subject
    ctx.staging.append(action)


# -- tool arg schemas ------------------------------------------------------ #
class BranchArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    branch: str = Field(description="Name of the new branch to create, e.g. 'fix/login-npe'.")
    base: str = Field(default="", description="Branch to start from. Empty means the repo's default branch.")


class CommitArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    branch: str = Field(description="Branch to commit onto (the one you created).")
    path: str = Field(description="File path within the repo to write, e.g. 'src/auth.py'.")
    content: str = Field(description="The COMPLETE new contents of the file (it replaces the whole file). Read the current file first, then supply the full modified version.")
    message: str = Field(description="Commit message.")


class PrArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    head: str = Field(description="The branch with your changes (the one you committed to).")
    base: str = Field(default="", description="Branch to merge into. Empty means the repo's default branch.")
    title: str = Field(description="Pull request title.")
    body: str = Field(default="", description="Pull request description. Reference the issue being fixed, e.g. 'Fixes #12'.")


class SubmitArgs(BaseModel):
    summary: str = Field(default="", description="Optional one-line summary of the change for the approval card.")


# -- tool bodies ----------------------------------------------------------- #
def _create_branch(repo: str, branch: str, base: str = "") -> str:
    _stage(fixer.branch_action(branch, base), repo)
    return (
        f"Staged: create branch '{branch}' in {repo}. Nothing is created yet. "
        f"Stage commits with commit_code, then open_pr, then call submit_change "
        f"to post one approval card."
    )


def _commit_code(repo: str, branch: str, path: str, content: str, message: str) -> str:
    _stage(fixer.commit_action(branch, path, content, message), repo)
    return (
        f"Staged: commit '{path}' on '{branch}' in {repo}. Still nothing written — "
        f"add more commits or open_pr, then submit_change."
    )


def _open_pr(repo: str, head: str, title: str, base: str = "", body: str = "") -> str:
    _stage(fixer.pr_action(head, base, title, body), repo)
    return (
        f"Staged: open PR from '{head}' in {repo}. Call submit_change to post the "
        f"approval card for the whole change."
    )


def _submit_change(summary: str = "") -> str:
    ctx = current_turn()
    if not ctx.staging:
        return (
            "Nothing is staged. Use create_branch / commit_code / open_pr first, "
            "then call submit_change."
        )
    payload = ProposalPayload(
        capability="fixer", subject=ctx.staging_subject, actions=list(ctx.staging)
    )
    line = summary or _default_summary(payload)
    # Clear staging so a later turn starts clean even if posting raises.
    ctx.staging = []
    ctx.staging_subject = ""
    return post_proposal(payload, line)


def _default_summary(payload: ProposalPayload) -> str:
    c = payload.counts()
    parts = []
    if c.get("create_branch"):
        parts.append("create a branch")
    if c.get("commit_file"):
        n = c["commit_file"]
        parts.append(f"commit {n} file" + ("s" if n > 1 else ""))
    if c.get("open_pr"):
        parts.append("open a PR")
    return " and ".join(parts) if parts else payload.summary_line()


def build_write_tools() -> list[StructuredTool]:
    """The fixer's tools: three staging steps plus the bundling submit."""
    return [
        StructuredTool.from_function(
            func=_create_branch,
            name="create_branch",
            description=(
                "Stage creating a new branch in a GitHub repo (the first step of a "
                "fix). Nothing is created until the change is submitted and a human "
                "approves. Provide repo, the new branch name, and optionally a base."
            ),
            args_schema=BranchArgs,
        ),
        StructuredTool.from_function(
            func=_commit_code,
            name="commit_code",
            description=(
                "Stage committing a file's full new contents onto a branch. Read the "
                "current file first (read_file) and supply the COMPLETE modified file. "
                "Nothing is written until submitted and approved."
            ),
            args_schema=CommitArgs,
        ),
        StructuredTool.from_function(
            func=_open_pr,
            name="open_pr",
            description=(
                "Stage opening a pull request from your branch into the base branch. "
                "Reference the issue in the body (e.g. 'Fixes #12'). Nothing is opened "
                "until submitted and approved."
            ),
            args_schema=PrArgs,
        ),
        StructuredTool.from_function(
            func=_submit_change,
            name="submit_change",
            description=(
                "Finalize the staged fix (branch + commits + PR) into ONE approval "
                "card in the thread. Call this last, after staging the steps. A human "
                "approves it, and only then does the runner make the changes in order."
            ),
            args_schema=SubmitArgs,
        ),
    ]
