"""Build the write actions for fixing an issue: a branch, a commit, a PR.

These are pure builders — given parameters, they return provider-agnostic
``Action`` objects naming the ``github_repo`` provider. They perform NO I/O and
import nothing from the runner: the agent only ever *describes* a write. The
runner's ``github_repo`` executor is the single place these are actually carried
out, and only after a human approves the proposal in Slack.

Bulky or structured parameters (file content, commit message, PR body, base
branch) live in ``Action.args`` so they never bloat the Slack approval card,
which renders only type/target/value/rationale/evidence.
"""
from __future__ import annotations

from warden_common.schemas import Action

PROVIDER = "github_repo"


def branch_action(branch: str, base: str = "", *, rationale: str = "") -> Action:
    """Create ``branch`` off ``base`` (empty ``base`` = the repo's default branch)."""
    return Action(
        provider=PROVIDER,
        type="create_branch",
        target=branch,
        value=f"from {base}" if base else "from default branch",
        args={"base": base},
        rationale=rationale or f"create branch {branch}",
    )


def commit_action(
    branch: str, path: str, content: str, message: str, *, rationale: str = ""
) -> Action:
    """Commit the full new contents of ``path`` onto ``branch``.

    ``content`` is the complete file (the GitHub Contents API replaces the whole
    file), so the brain — having read the current file via the explorer tools —
    supplies the modified file in full.
    """
    return Action(
        provider=PROVIDER,
        type="commit_file",
        target=path,
        value=f"on {branch}",
        args={"branch": branch, "content": content, "message": message},
        rationale=rationale or message or f"commit {path}",
    )


def pr_action(
    head: str, base: str = "", title: str = "", body: str = "", *, rationale: str = ""
) -> Action:
    """Open a pull request from ``head`` into ``base`` (empty = default branch)."""
    return Action(
        provider=PROVIDER,
        type="open_pr",
        target=head,
        value=f"→ {base}" if base else "→ default branch",
        args={"base": base, "title": title, "body": body},
        rationale=rationale or title or f"open PR from {head}",
    )
