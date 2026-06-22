"""Capability registry package.

Importing this package registers all built-in capabilities (their modules call
``register()`` at import time). The surfaces import from here, so a new
capability becomes available everywhere just by adding its import below.
"""
from __future__ import annotations

from .base import Capability, all_capabilities, get, names, register

# --- built-in capabilities (each registers itself on import) ----------------
from . import triage  # noqa: F401,E402  (side-effect: registers "triage")

# Read-only tooling (not a Capability): registers the explorer's repo-read tools.
from . import explorer  # noqa: F401,E402  (side-effect: registers read-only repo tools)

__all__ = ["Capability", "register", "get", "all_capabilities", "names"]
