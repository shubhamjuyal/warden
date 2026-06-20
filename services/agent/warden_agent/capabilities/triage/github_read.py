"""Read-only GitHub client for the triage capability.

Note what is *absent*: there is no method here that mutates anything. The agent
can list and read issues; it has no code path to label, assign, or close. Even
if its token were write-scoped (it should not be), the agent has no write call
to make.
"""
from __future__ import annotations

import httpx

API = "https://api.github.com"


class Issue:
    def __init__(self, raw: dict):
        self.number: int = raw["number"]
        self.title: str = raw.get("title", "")
        self.body: str = raw.get("body") or ""
        self.labels: list[str] = [
            label["name"] if isinstance(label, dict) else label
            for label in raw.get("labels", [])
        ]
        self.author: str = (raw.get("user") or {}).get("login", "")

    def to_prompt_dict(self) -> dict:
        # Trim the body so we don't blow the context window on long issues.
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body[:1500],
            "existing_labels": self.labels,
        }


class GitHubReadClient:
    def __init__(self, token: str, *, base_url: str = API, timeout: float = 15.0):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    def list_open_issues(self, repo: str, *, limit: int = 50) -> list[Issue]:
        issues: list[Issue] = []
        page = 1
        while len(issues) < limit:
            r = self._client.get(
                f"/repos/{repo}/issues",
                params={"state": "open", "per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for raw in batch:
                # The issues endpoint also returns PRs; skip them.
                if "pull_request" in raw:
                    continue
                issues.append(Issue(raw))
                if len(issues) >= limit:
                    break
            page += 1
        return issues

    def close(self) -> None:
        self._client.close()
