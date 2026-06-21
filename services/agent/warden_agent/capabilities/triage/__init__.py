"""The triage capability — Warden's first capability.

For each open GitHub issue it proposes exactly one standard label (bug,
documentation, duplicate, enhancement, good first issue, invalid, question) and,
where there's a clear fit, an assignee drawn from the repo's collaborators — all
for human approval. Registers itself on import.
"""
from __future__ import annotations

from warden_common.schemas import ProposalPayload

from ..base import Capability, register
from .deps import build_classifier, build_reader
from .graph import run_triage


class TriageCapability(Capability):
    name = "triage"
    help = "Classify, label, assign, and dedupe open GitHub issues for a repository."
    subject_description = (
        "The GitHub repository to triage, formatted as 'owner/repo' "
        "(e.g. 'acme/payments')."
    )

    def run(self, *, subject: str, requested_by: str) -> ProposalPayload:
        reader = build_reader()
        classifier = build_classifier()
        try:
            return run_triage(
                reader, classifier, subject=subject, requested_by=requested_by
            )
        finally:
            reader.close()

    def summarize(self, payload: ProposalPayload) -> str:
        c = payload.counts()
        return (
            f"apply {c.get('label', 0)} labels and assign {c.get('assign', 0)} issues"
        )


register(TriageCapability())
