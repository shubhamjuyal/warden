"""Unit tests for the explorer's read-only GitHub client.

No network: an httpx ``MockTransport`` answers requests, so we exercise the real
client (headers, params, ``raise_for_status``) while scripting GitHub's replies.
We assert the guards that protect the brain — file-size truncation, dir-vs-file
handling, friendly errors on 404 — and that ``search_code`` builds the right
``q``.
"""
from __future__ import annotations

import base64

import httpx
import pytest

from warden_agent.capabilities.explorer.repo_reader import API, GitHubRepoReader


def _reader(handler) -> GitHubRepoReader:
    """A reader whose underlying client routes through a mock transport."""
    r = GitHubRepoReader("ghp_read")
    r._client = httpx.Client(
        base_url=API,
        transport=httpx.MockTransport(handler),
        headers={"X-GitHub-Api-Version": "2022-11-28"},
    )
    return r


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_read_file_decodes_base64():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"size": 5, "encoding": "base64", "content": _b64("hello")})

    out = _reader(handler).read_file("acme/api", "README.md")
    assert out == {"path": "README.md", "size": 5, "truncated": False, "content": "hello"}


def test_read_file_size_guard_skips_decode():
    # A file larger than max_bytes is never decoded — content is empty, flagged.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"size": 500_000, "encoding": "base64", "content": _b64("x")})

    out = _reader(handler).read_file("acme/api", "big.bin", max_bytes=100_000)
    assert out["truncated"] is True
    assert out["content"] == ""
    assert out["size"] == 500_000


def test_browse_dir_handles_file_response():
    # GitHub returns a dict (not a list) when the path is a file, not a directory.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "app.py", "size": 12, "path": "src/app.py"})

    out = _reader(handler).browse_dir("acme/api", "src/app.py")
    assert out == [{"name": "app.py", "type": "file", "size": 12, "path": "src/app.py"}]


def test_browse_dir_lists_directory():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"name": "app.py", "type": "file", "size": 12, "path": "src/app.py"},
            {"name": "lib", "type": "dir", "size": 0, "path": "src/lib"},
        ])

    out = _reader(handler).browse_dir("acme/api", "src")
    assert [e["name"] for e in out] == ["app.py", "lib"]


def test_404_yields_friendly_error_not_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    reader = _reader(handler)
    assert "not found" in reader.repo_overview("acme/missing")["error"]
    assert reader.browse_dir("acme/api", "nope")[0]["error"]
    assert reader.read_file("acme/api", "nope.py")["error"]
    assert reader.list_branches("acme/missing") == []


def test_search_code_builds_repo_scoped_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params.get("q")
        return httpx.Response(200, json={"items": [
            {"path": "src/auth.py", "name": "auth.py", "html_url": "http://x/auth.py"},
        ]})

    out = _reader(handler).search_code("acme/api", "login")
    assert seen["q"] == "login repo:acme/api"
    assert out == [{"path": "src/auth.py", "name": "auth.py", "html_url": "http://x/auth.py"}]


def test_list_issues_filters_out_pull_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[
                {"number": 1, "title": "real issue", "state": "open", "labels": [{"name": "bug"}], "user": {"login": "alice"}, "comments": 2},
                {"number": 2, "title": "a PR", "state": "open", "pull_request": {"url": "x"}, "user": {"login": "bob"}},
            ])
        return httpx.Response(200, json=[])  # no more pages

    out = _reader(handler).list_issues("acme/api")
    assert out["count"] == 1  # the PR is excluded
    assert out["capped"] is False
    assert out["issues"][0] == {
        "number": 1, "title": "real issue", "state": "open",
        "labels": ["bug"], "author": "alice", "comments": 2,
    }


def test_recent_commits_summarizes_first_line():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"sha": "abcdef1234", "commit": {"message": "fix bug\n\ndetails", "author": {"name": "alice", "date": "2026-06-01T00:00:00Z"}}},
        ])

    out = _reader(handler).recent_commits("acme/api")
    assert out == [{"sha": "abcdef1", "message": "fix bug", "author": "alice", "date": "2026-06-01T00:00:00Z"}]
