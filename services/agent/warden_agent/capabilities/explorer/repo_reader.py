"""Read-only GitHub client for the repository explorer.

Like the triage reader, note what is *absent*: every method here is a ``GET``.
There is no code path that labels, assigns, closes, commits, or pushes. The
explorer lets the agent *read* any part of a repo — code, files, trees,
branches, commits, metadata — and nothing more, even if its token were
write-scoped (it should not be).

Each method translates GitHub's HTTP errors into a clean structured value (a
dict with an ``error`` key, or an empty list) so a hijacked or fat-fingered
question yields a friendly message in Slack rather than a stack trace — the same
defensive spirit as triage's ``list_assignees`` returning ``[]``.
"""
from __future__ import annotations

import base64

import httpx

API = "https://api.github.com"

#: Decoded text files larger than this are truncated before reaching the brain,
#: so one big file can't blow the model's context window (triage trims issue
#: bodies to 1500 chars for the same reason).
_MAX_TEXT_CHARS = 20_000


class GitHubRepoReader:
    def __init__(self, token: str, *, base_url: str = API, timeout: float = 15.0):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    # -- metadata ---------------------------------------------------------- #
    def repo_overview(self, repo: str) -> dict:
        """High-level facts about a repo: description, default branch, language,
        stars, topics, license. The default branch here is what the other
        methods fall back to when no ``ref`` is given."""
        try:
            r = self._client.get(f"/repos/{repo}")
            r.raise_for_status()
        except httpx.HTTPError:
            return {"error": f"repo '{repo}' not found or not visible to this token"}
        d = r.json()
        return {
            "full_name": d.get("full_name", repo),
            "description": d.get("description") or "",
            "default_branch": d.get("default_branch", ""),
            "language": d.get("language") or "",
            "stars": d.get("stargazers_count", 0),
            "topics": d.get("topics", []),
            "license": (d.get("license") or {}).get("spdx_id") or "",
            "pushed_at": d.get("pushed_at", ""),
            "archived": d.get("archived", False),
        }

    # -- branches ---------------------------------------------------------- #
    def list_branches(self, repo: str, *, limit: int = 50) -> list[str]:
        """Branch names in the repo. Returns [] if not visible to this token."""
        try:
            r = self._client.get(
                f"/repos/{repo}/branches", params={"per_page": limit}
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return []
        return [b["name"] for b in r.json() if b.get("name")][:limit]

    # -- tree / files ------------------------------------------------------ #
    def browse_dir(
        self, repo: str, path: str = "", ref: str | None = None, *, limit: int = 200
    ) -> list[dict]:
        """List a directory's entries (name, type, size, path). If ``path`` is
        actually a file, returns a single entry flagged ``type='file'`` so the
        caller knows to ``read_file`` instead."""
        params = {"ref": ref} if ref else None
        try:
            r = self._client.get(f"/repos/{repo}/contents/{path}", params=params)
            r.raise_for_status()
        except httpx.HTTPError:
            return [{"error": f"path '{path}' not found in {repo}"}]
        data = r.json()
        if isinstance(data, dict):  # path pointed at a file, not a directory
            return [{
                "name": data.get("name", path),
                "type": "file",
                "size": data.get("size", 0),
                "path": data.get("path", path),
            }]
        return [
            {
                "name": e.get("name", ""),
                "type": e.get("type", ""),
                "size": e.get("size", 0),
                "path": e.get("path", ""),
            }
            for e in data
        ][:limit]

    def read_file(
        self, repo: str, path: str, ref: str | None = None, *, max_bytes: int = 100_000
    ) -> dict:
        """Fetch one file's text. Large or binary files are not decoded — the
        result carries ``truncated=True`` and empty ``content`` instead, so the
        brain never ingests a megabyte blob."""
        params = {"ref": ref} if ref else None
        try:
            r = self._client.get(f"/repos/{repo}/contents/{path}", params=params)
            r.raise_for_status()
        except httpx.HTTPError:
            return {"error": f"file '{path}' not found in {repo}"}
        d = r.json()
        if isinstance(d, list):
            return {"error": f"'{path}' is a directory — use browse_dir"}
        size = d.get("size", 0)
        if size > max_bytes or d.get("encoding") != "base64" or not d.get("content"):
            return {"path": path, "size": size, "truncated": True, "content": ""}
        text = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
        truncated = len(text) > _MAX_TEXT_CHARS
        return {
            "path": path,
            "size": size,
            "truncated": truncated,
            "content": text[:_MAX_TEXT_CHARS],
        }

    # -- issues ------------------------------------------------------------ #
    def list_issues(
        self, repo: str, state: str = "open", *, limit: int = 100
    ) -> dict:
        """List a repo's issues (``state`` = open | closed | all), filtering out
        pull requests — GitHub's issues endpoint returns PRs too. Returns a
        ``count`` plus the issues; ``capped`` is True when there are more than
        ``limit`` (so the count is a floor, not exact)."""
        if state not in ("open", "closed", "all"):
            state = "open"
        issues: list[dict] = []
        page = 1
        capped = False
        while len(issues) < limit:
            try:
                r = self._client.get(
                    f"/repos/{repo}/issues",
                    params={"state": state, "per_page": 100, "page": page},
                )
                r.raise_for_status()
            except httpx.HTTPError:
                return {"error": f"issues for '{repo}' not found or not visible to this token"}
            batch = r.json()
            if not batch:
                break
            for raw in batch:
                if "pull_request" in raw:  # skip PRs
                    continue
                issues.append({
                    "number": raw.get("number"),
                    "title": raw.get("title", ""),
                    "state": raw.get("state", ""),
                    "labels": [
                        lbl["name"] if isinstance(lbl, dict) else lbl
                        for lbl in raw.get("labels", [])
                    ],
                    "author": (raw.get("user") or {}).get("login", ""),
                    "comments": raw.get("comments", 0),
                })
                if len(issues) >= limit:
                    capped = True
                    break
            page += 1
        return {"state": state, "count": len(issues), "capped": capped, "issues": issues}

    # -- search ------------------------------------------------------------ #
    def search_code(self, repo: str, query: str, *, limit: int = 20) -> list[dict]:
        """Search code within a single repo. Note: GitHub's code search needs
        the token to have access and has a stricter rate limit; an unavailable
        or invalid query yields a structured error rather than raising."""
        try:
            r = self._client.get(
                "/search/code",
                params={"q": f"{query} repo:{repo}", "per_page": limit},
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return [{"error": "code search unavailable or query invalid"}]
        return [
            {
                "path": item.get("path", ""),
                "name": item.get("name", ""),
                "html_url": item.get("html_url", ""),
            }
            for item in r.json().get("items", [])
        ]

    # -- history ----------------------------------------------------------- #
    def recent_commits(
        self,
        repo: str,
        ref: str | None = None,
        path: str | None = None,
        *,
        limit: int = 20,
    ) -> list[dict]:
        """Most recent commits, optionally scoped to a branch/SHA (``ref``) or a
        single ``path``."""
        params: dict = {"per_page": limit}
        if ref:
            params["sha"] = ref
        if path:
            params["path"] = path
        try:
            r = self._client.get(f"/repos/{repo}/commits", params=params)
            r.raise_for_status()
        except httpx.HTTPError:
            return []
        out = []
        for c in r.json():
            commit = c.get("commit", {})
            message = (commit.get("message") or "").splitlines()
            out.append({
                "sha": (c.get("sha") or "")[:7],
                "message": message[0] if message else "",
                "author": (commit.get("author") or {}).get("name", ""),
                "date": (commit.get("author") or {}).get("date", ""),
            })
        return out

    def close(self) -> None:
        self._client.close()
