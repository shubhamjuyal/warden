"""warden_agent — the sandboxed triage agent.

Read-only by construction. It reasons about issues and *proposes* actions, then
posts them to Slack for a human. It holds a read-only GitHub token and the
OpenAI key — never a write token. The one place writes could happen
(``warden_runner``) is a different package in a different container that this
process cannot import.
"""
