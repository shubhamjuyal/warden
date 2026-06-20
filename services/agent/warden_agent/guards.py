"""Startup guards that make the sandbox legible and self-enforcing.

The guiding principle: the only reliable way to prevent an agent from doing
something is to make it physically impossible. We can't make Python forget an
env var, but we can make the agent process *refuse to run* if it was handed a
write credential — turning a misconfiguration into a loud crash instead of a
silent capability. Combined with deploying the agent in its own container
without the secret, this keeps the separation honest.
"""
from __future__ import annotations

import os

# Names that, if present in the agent's environment, indicate a broken deploy:
# the agent should NEVER be able to see a write-scoped credential.
_FORBIDDEN_ENV = ("GITHUB_WRITE_TOKEN",)


class SandboxViolation(RuntimeError):
    pass


def assert_sandboxed(env: dict[str, str] | None = None) -> None:
    """Raise if the agent can see a credential it must never hold."""
    env = os.environ if env is None else env
    leaked = [name for name in _FORBIDDEN_ENV if env.get(name)]
    if leaked:
        raise SandboxViolation(
            "Agent sandbox violated: write credential(s) present in the agent "
            f"environment: {', '.join(leaked)}. The agent must never hold a "
            "write token — that capability belongs only to the runner. "
            "Refusing to start."
        )
