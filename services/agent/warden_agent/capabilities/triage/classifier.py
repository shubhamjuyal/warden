"""Issue classification with OpenAI.

The triage capability's reasoning lives here. For each open issue it picks exactly
ONE standard GitHub label and, when there's a clear fit, a repo collaborator to
assign — each with a short rationale and a quoted piece of evidence, because a weak
approval step is just a button with no context. The rationale and evidence are what
make the eventual Slack approval card legible.
"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .types import LABEL_DESCRIPTIONS, IssueClassification


class ClassificationBatch(BaseModel):
    items: list[IssueClassification]


_LABEL_MENU = "\n".join(f"- {name} — {desc}" for name, desc in LABEL_DESCRIPTIONS.items())

SYSTEM_PROMPT = f"""You are Warden, a GitHub issue triage assistant.
You are given the open issues for one repository. For EACH issue decide:

- label: choose exactly ONE label, and it MUST be one of these:
{_LABEL_MENU}
  Pick the single best fit. Use "duplicate" only when the issue clearly restates
  another; "invalid" when it isn't actionable or doesn't make sense; "question"
  when the reporter is really just asking something.

- assignee: a GitHub login to assign the issue to, chosen ONLY from the provided
  list of repository collaborators. Pick one when the issue plausibly suits them
  (their apparent area/ownership, or they're the reporter and can act on it).
  If no one is a clear fit, or the list is empty, use null. NEVER invent a login
  that isn't in the provided list.

- rationale: one sentence explaining the label (and the assignee, if any).
- evidence: a short quote or signal from the issue that supports it.

Be conservative and make each suggestion easy for a human to verify. Return one
classification object per issue, preserving issue_number."""


class Classifier(Protocol):
    def classify(
        self, repo: str, issues: list[dict], assignees: list[str]
    ) -> list[IssueClassification]: ...


class LLMClassifier:
    """Real OpenAI classifier (the default in production)."""

    def __init__(self, *, api_key: str, model: str):
        if not api_key:
            raise RuntimeError(
                "LLMClassifier requires OPENAI_API_KEY. Set it, or inject a "
                "different Classifier for offline runs/tests."
            )
        # Imported lazily so the package imports cleanly without the dep present.
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            model=model, api_key=api_key, temperature=0, max_tokens=4096
        ).with_structured_output(ClassificationBatch)

    def classify(
        self, repo: str, issues: list[dict], assignees: list[str]
    ) -> list[IssueClassification]:
        if not issues:
            return []
        candidates = ", ".join(assignees) if assignees else "(none available)"
        human = (
            f"Repository: {repo}\n"
            f"Assignable collaborators: {candidates}\n\n"
            f"Classify these {len(issues)} open issues:\n"
            f"{_render_issues(issues)}"
        )
        result: ClassificationBatch = self._llm.invoke(
            [("system", SYSTEM_PROMPT), ("human", human)]
        )
        return result.items


def _render_issues(issues: list[dict]) -> str:
    import json

    return json.dumps(issues, indent=2)
