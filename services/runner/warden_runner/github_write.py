"""The single GitHub *write* client in the whole system.

If you are auditing this repo for "can the agent write to GitHub?", this file is
the answer: it is imported only by the runner, instantiated only with the
runner's write token, and never reachable from the agent process.
"""
from __future__ import annotations

import base64

import httpx

API = "https://api.github.com"


class GitHubWriteClient:
    def __init__(self, token: str, *, base_url: str = API, timeout: float = 15.0):
        if not token:
            # Fail loud: a runner with no write token is misconfigured. We do
            # NOT silently degrade, because that would hide a broken deploy.
            raise RuntimeError("runner started without GITHUB_WRITE_TOKEN")
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    # -- writes --------------------------------------------------------------
    def add_labels(self, repo: str, issue: int, labels: list[str]) -> None:
        r = self._client.post(f"/repos/{repo}/issues/{issue}/labels", json={"labels": labels})
        r.raise_for_status()

    def add_assignees(self, repo: str, issue: int, assignees: list[str]) -> None:
        r = self._client.post(
            f"/repos/{repo}/issues/{issue}/assignees", json={"assignees": assignees}
        )
        r.raise_for_status()

    def close_issue(self, repo: str, issue: int, *, reason: str = "not_planned") -> None:
        r = self._client.patch(
            f"/repos/{repo}/issues/{issue}",
            json={"state": "closed", "state_reason": reason},
        )
        r.raise_for_status()

    def comment(self, repo: str, issue: int, body: str) -> None:
        r = self._client.post(
            f"/repos/{repo}/issues/{issue}/comments", json={"body": body}
        )
        r.raise_for_status()

    # -- repo writes: branch / commit / PR (the github_repo provider) ---------
    def _default_branch(self, repo: str) -> str:
        r = self._client.get(f"/repos/{repo}")
        r.raise_for_status()
        return r.json().get("default_branch", "main")

    def create_branch(self, repo: str, branch: str, base: str = "") -> None:
        """Create ``branch`` pointing at the tip of ``base`` (default branch if
        empty). Idempotent: an already-existing branch is left as-is."""
        base = base or self._default_branch(repo)
        r = self._client.get(f"/repos/{repo}/git/ref/heads/{base}")
        r.raise_for_status()
        sha = r.json()["object"]["sha"]
        r2 = self._client.post(
            f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}
        )
        if r2.status_code == 422:  # "Reference already exists" — fine, reuse it
            return
        r2.raise_for_status()

    def commit_file(
        self, repo: str, branch: str, path: str, content: str, message: str
    ) -> None:
        """Create or replace ``path`` on ``branch`` with ``content`` in one commit.

        The Contents API needs the current blob SHA to overwrite an existing file,
        so we look it up first (absent for a brand-new file)."""
        sha: str | None = None
        g = self._client.get(f"/repos/{repo}/contents/{path}", params={"ref": branch})
        if g.status_code == 200 and isinstance(g.json(), dict):
            sha = g.json().get("sha")
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        r = self._client.put(f"/repos/{repo}/contents/{path}", json=body)
        r.raise_for_status()

    def open_pr(
        self, repo: str, head: str, base: str = "", title: str = "", body: str = ""
    ) -> str:
        """Open a PR from ``head`` into ``base`` (default branch if empty). Returns
        the PR's html_url."""
        base = base or self._default_branch(repo)
        r = self._client.post(
            f"/repos/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )
        r.raise_for_status()
        return r.json().get("html_url", "")

    def close(self) -> None:
        self._client.close()
