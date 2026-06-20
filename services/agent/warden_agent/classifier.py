"""Issue classification with OpenAI.

The agent's reasoning lives here. It reads each open issue and proposes a
severity, an area/team, labels, an assignee, and possible duplicates — with a
short rationale and a quoted piece of evidence for each, because a weak approval
step is just a button with no context. The rationale and evidence are what make
the eventual Slack approval card legible.
"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from warden_common.schemas import IssueClassification


class ClassificationBatch(BaseModel):
    items: list[IssueClassification]


SYSTEM_PROMPT = """You are Warden, a senior engineering triage assistant.
You are given a list of open GitHub issues for one repository. For EACH issue,
decide:
- severity: one of critical | high | medium | low
- area: a short team/area label (e.g. backend, frontend, infra, docs, auth)
- suggested_labels: 1-3 concrete labels to apply (include a severity label like
  "severity:high" and an area label like "area:backend")
- suggested_assignee: a GitHub login if one is strongly implied by CODEOWNERS-style
  hints in the issue, otherwise null. Do not invent assignees.
- duplicate_of: the issue NUMBER this clearly duplicates, or null. Only mark a
  duplicate when the overlap is unmistakable.
- rationale: one sentence explaining the call.
- evidence: a short quote or signal from the issue that supports it.

Be conservative: when unsure, prefer lower severity and no assignee. A human will
approve or reject your proposal, so make each suggestion easy to verify.
Return one classification object per issue, preserving issue_number."""


class Classifier(Protocol):
    def classify(self, repo: str, issues: list[dict]) -> list[IssueClassification]: ...


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

    def classify(self, repo: str, issues: list[dict]) -> list[IssueClassification]:
        if not issues:
            return []
        human = (
            f"Repository: {repo}\n\nClassify these {len(issues)} open issues:\n"
            f"{_render_issues(issues)}"
        )
        result: ClassificationBatch = self._llm.invoke(
            [("system", SYSTEM_PROMPT), ("human", human)]
        )
        return result.items


def _render_issues(issues: list[dict]) -> str:
    import json

    return json.dumps(issues, indent=2)
