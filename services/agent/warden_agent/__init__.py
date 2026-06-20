"""warden_agent — the sandboxed agent.

Read-only by construction. It runs **capabilities** (triage today; more later)
that reason about a subject and *propose* consequential actions, then present
them in Slack for a human. It holds a read-only GitHub token and the model key —
never a write token. The one place writes could happen (``warden_runner``) is a
different package in a different container that this process cannot import.

Layout:
    capabilities/   the things Warden can do; each registers itself
    surfaces/       how humans reach it (Slack, CLI) — capability-agnostic
    deps.py         shared wiring (the runner client)
    guards.py       startup sandbox assertions
"""
