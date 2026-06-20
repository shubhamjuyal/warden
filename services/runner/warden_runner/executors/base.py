"""Registry + the generic execution loop.

The loop is capability-agnostic: it walks the approved actions and dispatches
each to the executor named by ``action.provider``. An unknown provider fails
that one action (recorded in the result) without aborting the rest.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from warden_common.schemas import Action, ExecutedAction, ProposalPayload


@runtime_checkable
class ProviderExecutor(Protocol):
    """A write surface for one provider (e.g. GitHub issues)."""

    provider: str

    def execute(self, subject: str, action: Action) -> tuple[bool, str]:
        """Perform ``action`` against ``subject``; return (ok, human detail)."""
        ...


class Registry:
    def __init__(self) -> None:
        self._by_provider: dict[str, ProviderExecutor] = {}

    def register(self, executor: ProviderExecutor) -> None:
        self._by_provider[executor.provider] = executor

    def get(self, provider: str) -> ProviderExecutor:
        if provider not in self._by_provider:
            raise KeyError(provider)
        return self._by_provider[provider]

    def providers(self) -> list[str]:
        return list(self._by_provider)


def execute_proposal(payload: ProposalPayload, registry: Registry) -> list[ExecutedAction]:
    """Execute every action in an already-approved proposal.

    This performs exactly the actions recorded in the ledger — it does not
    decide *whether* to act (the approval gate already did).
    """
    results: list[ExecutedAction] = []
    for action in payload.actions:
        try:
            executor = registry.get(action.provider)
        except KeyError:
            results.append(
                ExecutedAction(
                    action=action,
                    ok=False,
                    detail=f"no executor registered for provider '{action.provider}'",
                )
            )
            continue
        try:
            ok, detail = executor.execute(payload.subject, action)
        except Exception as exc:  # noqa: BLE001 - surface any failure per-action
            ok, detail = False, f"error: {exc}"
        results.append(ExecutedAction(action=action, ok=ok, detail=detail))
    return results
