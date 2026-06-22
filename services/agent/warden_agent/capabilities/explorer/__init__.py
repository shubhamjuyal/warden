"""The repository explorer — Warden's read-only window into any repo.

A set of read-only tools (repo metadata, branches, directory listings, file
contents, code search, recent commits) the conversational brain calls to answer
questions about a repository's data. Importing this package registers those tools
(``tools.py`` calls ``register_readonly`` at import time), exactly like the triage
capability self-registers.

This is *not* a :class:`~warden_agent.capabilities.base.Capability`: it proposes
nothing and writes nothing, so it lives in its own read-only registry rather than
the capability/approval path.
"""
from __future__ import annotations

from . import tools  # noqa: F401  (side-effect: registers the read-only tools)
from .registry import all_readonly_tools

__all__ = ["all_readonly_tools"]
