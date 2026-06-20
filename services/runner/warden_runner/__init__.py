"""warden_runner — the permissioned execution runner.

This is the ONLY component in Warden that holds a write-scoped GitHub token and
the ONLY place a GitHub write call is implemented (see ``github_write.py``). The
agent can ask this service to act; it cannot act itself, and it cannot import
this package across the process/container boundary.
"""
