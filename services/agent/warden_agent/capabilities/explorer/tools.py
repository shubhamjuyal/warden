"""The repository-explorer tools — Warden's read-only window into a repo.

Each function here is a LangChain ``StructuredTool`` the brain can call to read
GitHub: repo metadata, branches, directory listings, file contents, code search,
and recent commits. Unlike a capability tool, these:

  * take rich arguments (repo, path, ref, query), not a single ``subject``;
  * return data as a string the brain relays — they never persist a proposal,
    never post an approval card, and never need the Slack turn context;
  * touch only ``GET`` endpoints via :func:`build_repo_reader`.

So "what branches does acme/api have?" or "show me its README" is answered inline
in the thread, with no Approve/Deny step — reading is free; only writes (triage)
need approval.
"""
from __future__ import annotations

import json
from typing import Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .deps import build_repo_reader
from .registry import register_readonly


def _with_reader(call: Callable) -> object:
    """Run ``call(reader)`` against a fresh read client, always closing it."""
    reader = build_repo_reader()
    try:
        return call(reader)
    finally:
        reader.close()


def _dump(value: object) -> str:
    """Compact JSON the model can read back to the user. Kept small by the
    reader's own caps (listing limits, file truncation)."""
    return json.dumps(value, ensure_ascii=False, indent=2)


# -- arg schemas ----------------------------------------------------------- #
class RepoArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo', e.g. 'acme/api'.")


class BrowseArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    path: str = Field(default="", description="Directory path within the repo. Empty means the repo root.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA. Defaults to the repo's default branch.")


class ReadFileArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    path: str = Field(description="Path to the file within the repo, e.g. 'src/app.py'.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or commit SHA. Defaults to the default branch.")


class ListIssuesArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    state: str = Field(default="open", description="Which issues: 'open', 'closed', or 'all'. Defaults to open.")


class SearchArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo' to search within.")
    query: str = Field(description="Code search terms, e.g. a function name or string to find.")


class CommitsArgs(BaseModel):
    repo: str = Field(description="GitHub repository as 'owner/repo'.")
    ref: str | None = Field(default=None, description="Optional branch, tag, or SHA. Defaults to the default branch.")
    path: str | None = Field(default=None, description="Optional path to scope history to a single file or directory.")


# -- tool bodies ----------------------------------------------------------- #
def _repo_overview(repo: str) -> str:
    return _dump(_with_reader(lambda r: r.repo_overview(repo)))


def _list_branches(repo: str) -> str:
    branches = _with_reader(lambda r: r.list_branches(repo))
    if not branches:
        return f"No branches visible for {repo} (or the repo isn't accessible)."
    return _dump(branches)


def _browse_dir(repo: str, path: str = "", ref: str | None = None) -> str:
    return _dump(_with_reader(lambda r: r.browse_dir(repo, path, ref)))


def _read_file(repo: str, path: str, ref: str | None = None) -> str:
    return _dump(_with_reader(lambda r: r.read_file(repo, path, ref)))


def _list_issues(repo: str, state: str = "open") -> str:
    result = _with_reader(lambda r: r.list_issues(repo, state))
    if isinstance(result, dict) and not result.get("error") and result.get("count") == 0:
        return f"{repo} has no {state} issues."
    return _dump(result)


def _search_code(repo: str, query: str) -> str:
    hits = _with_reader(lambda r: r.search_code(repo, query))
    if not hits:
        return f"No code matches for '{query}' in {repo}."
    return _dump(hits)


def _recent_commits(repo: str, ref: str | None = None, path: str | None = None) -> str:
    commits = _with_reader(lambda r: r.recent_commits(repo, ref, path))
    if not commits:
        return f"No commits found for {repo}."
    return _dump(commits)


# -- registration ---------------------------------------------------------- #
_TOOLS = [
    StructuredTool.from_function(
        func=_repo_overview,
        name="repo_overview",
        description=(
            "Get high-level facts about a GitHub repo: description, default branch, "
            "primary language, stars, topics, license. Use this first when the user "
            "asks broadly about a repo or you need its default branch."
        ),
        args_schema=RepoArgs,
    ),
    StructuredTool.from_function(
        func=_list_branches,
        name="list_branches",
        description=(
            "List the branch names of a GitHub repo. Use when the user asks what "
            "branches exist."
        ),
        args_schema=RepoArgs,
    ),
    StructuredTool.from_function(
        func=_browse_dir,
        name="browse_dir",
        description=(
            "List the files and subfolders in a directory of a GitHub repo. Use to "
            "explore the layout or find where something lives before reading a file. "
            "Empty path lists the repo root; optional ref selects a branch/tag/SHA."
        ),
        args_schema=BrowseArgs,
    ),
    StructuredTool.from_function(
        func=_read_file,
        name="read_file",
        description=(
            "Read one file's contents from a GitHub repo. Use when the user asks "
            "what's in a specific file. Large or binary files come back truncated. "
            "Provide repo and path; optional ref selects a branch/tag/SHA."
        ),
        args_schema=ReadFileArgs,
    ),
    StructuredTool.from_function(
        func=_list_issues,
        name="list_issues",
        description=(
            "List a repo's issues and their count, by state (open, closed, or all). "
            "Use when the user asks how many issues there are, or to see/summarize "
            "open or closed issues. Pull requests are excluded. The result's 'count' "
            "is exact unless 'capped' is true (very large repos)."
        ),
        args_schema=ListIssuesArgs,
    ),
    StructuredTool.from_function(
        func=_search_code,
        name="search_code",
        description=(
            "Search code within a single GitHub repo for terms (a symbol, function "
            "name, or string). Use to locate where something is implemented before "
            "reading whole files."
        ),
        args_schema=SearchArgs,
    ),
    StructuredTool.from_function(
        func=_recent_commits,
        name="recent_commits",
        description=(
            "List recent commits in a GitHub repo, optionally scoped to a branch/SHA "
            "(ref) or a single path. Use when the user asks what changed recently."
        ),
        args_schema=CommitsArgs,
    ),
]

for _tool in _TOOLS:
    register_readonly(_tool)
