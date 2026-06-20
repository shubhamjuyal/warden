"""Slack Block Kit rendering for an approval card.

Capability-agnostic: it renders any ``ProposalPayload`` — the capability supplies
a human summary line, and each action shows its type/target/value plus the
rationale and evidence that make the approval legible.
"""
from __future__ import annotations

from warden_common.schemas import ProposalPayload


def proposal_blocks(proposal_id: str, payload: ProposalPayload, summary: str) -> list[dict]:
    header = (
        f"*Warden · {payload.capability}* proposal for `{payload.subject}`\n"
        f"I want to {summary}. Approve?"
    )
    counts = payload.counts()
    counts_text = "   ".join(f"{n} {t}" for t, n in counts.items()) or "no actions"

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": counts_text}]},
    ]

    # Show up to 8 actions inline so the approver has context, not just a button.
    for action in payload.actions[:8]:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"• *{action.type}* on {action.target}"
                        + (f" → `{action.value}`" if action.value else "")
                        + f"\n   _{action.rationale}_"
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
