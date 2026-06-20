"""Turn an approved proposal payload into GitHub writes.

The executor is deliberately dumb: it does not decide *whether* to act (the
ledger gate already did) — it only performs the exact actions recorded in the
proposal, one by one, and reports the outcome of each for the audit trail.
"""
from __future__ import annotations

from typing import Protocol

from warden_common.schemas import ActionType, ExecutedAction, IssueAction, ProposalPayload


class Writer(Protocol):
    def add_labels(self, repo: str, issue: int, labels: list[str]) -> None: ...
    def add_assignees(self, repo: str, issue: int, assignees: list[str]) -> None: ...
    def close_issue(self, repo: str, issue: int, *, reason: str = ...) -> None: ...
    def comment(self, repo: str, issue: int, body: str) -> None: ...


def execute_proposal(payload: ProposalPayload, writer: Writer) -> list[ExecutedAction]:
    repo = payload.repo
    results: list[ExecutedAction] = []
    for action in payload.actions:
        results.append(_execute_one(repo, action, writer))
    return results


def _execute_one(repo: str, action: IssueAction, writer: Writer) -> ExecutedAction:
    try:
        if action.type == ActionType.LABEL:
            writer.add_labels(repo, action.issue_number, [action.value])
            detail = f"labeled #{action.issue_number} '{action.value}'"
        elif action.type == ActionType.ASSIGN:
            writer.add_assignees(repo, action.issue_number, [action.value])
            detail = f"assigned #{action.issue_number} -> {action.value}"
        elif action.type == ActionType.CLOSE:
            if action.value:
                writer.comment(
                    repo,
                    action.issue_number,
                    f"Closing as a duplicate of #{action.value}. "
                    f"— triaged by Warden, approved via the permission ledger.",
                )
            writer.close_issue(repo, action.issue_number, reason="not_planned")
            detail = f"closed #{action.issue_number}" + (
                f" (dup of #{action.value})" if action.value else ""
            )
        else:  # pragma: no cover - schema constrains this
            return ExecutedAction(action=action, ok=False, detail="unknown action type")
        return ExecutedAction(action=action, ok=True, detail=detail)
    except Exception as exc:  # noqa: BLE001 - surface any write failure per-action
        return ExecutedAction(action=action, ok=False, detail=f"error: {exc}")
