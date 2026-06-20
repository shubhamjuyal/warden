"""The single GitHub *write* client in the whole system.

If you are auditing this repo for "can the agent write to GitHub?", this file is
the answer: it is imported only by the runner, instantiated only with the
runner's write token, and never reachable from the agent process.
"""
from __future__ import annotations

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

    def close(self) -> None:
        self._client.close()
