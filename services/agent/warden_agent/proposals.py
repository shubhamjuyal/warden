"""Turn classifications into a concrete proposal, and render the Slack card.

A proposal is the bundle of consequential writes the agent wants to make. The
human sees the *summary* and can drill into the per-action rationale/evidence —
exactly the proposed action + supporting evidence + next consequence that a
real approval step must show (a weak approval step is just a button with no
context).
"""
from __future__ import annotations

from warden_common.schemas import (
    ActionType,
    IssueAction,
    IssueClassification,
    ProposalPayload,
)


def build_payload(repo: str, classifications: list[IssueClassification]) -> ProposalPayload:
    actions: list[IssueAction] = []
    for c in classifications:
        # 1) Labels — severity + area + any extra suggested labels (deduped).
        labels: list[str] = []
        for lbl in (*c.suggested_labels, f"severity:{c.severity}", f"area:{c.area}"):
            if lbl and lbl not in labels:
                labels.append(lbl)
        for lbl in labels:
            actions.append(
                IssueAction(
                    type=ActionType.LABEL,
                    issue_number=c.issue_number,
                    value=lbl,
                    rationale=c.rationale or f"classified as {c.severity}/{c.area}",
                    evidence=c.evidence,
                )
            )
        # 2) Assignment — only if the model proposed one.
        if c.suggested_assignee:
            actions.append(
                IssueAction(
                    type=ActionType.ASSIGN,
                    issue_number=c.issue_number,
                    value=c.suggested_assignee,
                    rationale=f"area {c.area} -> {c.suggested_assignee}",
                    evidence=c.evidence,
                )
            )
        # 3) Close as duplicate — only the higher-numbered (newer) issue.
        if c.duplicate_of and c.duplicate_of < c.issue_number:
            actions.append(
                IssueAction(
                    type=ActionType.CLOSE,
                    issue_number=c.issue_number,
                    value=str(c.duplicate_of),
                    rationale=f"duplicate of #{c.duplicate_of}",
                    evidence=c.evidence,
                )
            )
    return ProposalPayload(repo=repo, actions=actions)


# --------------------------------------------------------------------------- #
# Slack Block Kit rendering
# --------------------------------------------------------------------------- #
def proposal_blocks(proposal_id: str, payload: ProposalPayload) -> list[dict]:
    c = payload.counts()
    header = (
        f"*Warden triage proposal* for `{payload.repo}`\n"
        f"I want to {payload.summary_line()}. Approve?"
    )
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f":label: {c['label']} labels   "
                        f":bust_in_silhouette: {c['assign']} assignments   "
                        f":wastebasket: {c['close']} closes"
                    ),
                }
            ],
        },
    ]

    # Show up to 8 actions inline so the approver has context, not just a button.
    for action in payload.actions[:8]:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"• *{action.type.value}* on #{action.issue_number}"
                        f" → `{action.value}`\n"
                        f"   _{action.rationale}_"
                        + (f"  ›  {action.evidence}" if action.evidence else "")
                    ),
                },
            }
        )
    if len(payload.actions) > 8:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"…and {len(payload.actions) - 8} more (full list in the audit dashboard).",
                    }
                ],
            }
        )

    blocks.append(
        {
            "type": "actions",
            "block_id": f"warden_decision::{proposal_id}",
            "elements": [
                _btn("Approve", "approve", proposal_id, style="primary"),
                _btn("Approve once", "approve_once", proposal_id),
                _btn("Deny", "deny", proposal_id, style="danger"),
                _btn("Standing rule", "standing_rule", proposal_id),
            ],
        }
    )
    return blocks


def _btn(text: str, decision: str, proposal_id: str, *, style: str | None = None) -> dict:
    el = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": f"decision_{decision}",
        "value": proposal_id,
    }
    if style:
        el["style"] = style
    return el
