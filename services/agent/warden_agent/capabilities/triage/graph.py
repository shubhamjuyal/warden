"""The LangGraph triage flow.

    fetch_issues → classify → dedupe → build_proposal

Each node is a pure-ish step over a shared state dict. The GitHub reader and the
classifier are injected, so the same graph runs against live GitHub + OpenAI in
production and against fakes in tests — without changing the flow.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from warden_common.schemas import ProposalPayload

from .build import build_payload
from .classifier import Classifier
from .github_read import GitHubReadClient
from .types import IssueClassification


class TriageState(TypedDict, total=False):
    subject: str          # "owner/repo"
    requested_by: str
    issues: list[dict]
    classifications: list[IssueClassification]
    payload: ProposalPayload


def build_graph(reader: GitHubReadClient, classifier: Classifier):
    def fetch_issues(state: TriageState) -> TriageState:
        issues = reader.list_open_issues(state["subject"])
        return {"issues": [i.to_prompt_dict() for i in issues]}

    def classify(state: TriageState) -> TriageState:
        items = classifier.classify(state["subject"], state.get("issues", []))
        return {"classifications": items}

    def dedupe(state: TriageState) -> TriageState:
        # Keep only duplicate links that point at an issue we actually saw, and
        # never let an issue be marked a duplicate of itself.
        seen = {i["number"] for i in state.get("issues", [])}
        cleaned: list[IssueClassification] = []
        for c in state.get("classifications", []):
            if c.duplicate_of is not None and (
                c.duplicate_of not in seen or c.duplicate_of == c.issue_number
            ):
                c = c.model_copy(update={"duplicate_of": None})
            cleaned.append(c)
        return {"classifications": cleaned}

    def make_proposal(state: TriageState) -> TriageState:
        payload = build_payload(state["subject"], state.get("classifications", []))
        return {"payload": payload}

    graph = StateGraph(TriageState)
    graph.add_node("fetch_issues", fetch_issues)
    graph.add_node("classify", classify)
    graph.add_node("dedupe", dedupe)
    graph.add_node("build_proposal", make_proposal)

    graph.add_edge(START, "fetch_issues")
    graph.add_edge("fetch_issues", "classify")
    graph.add_edge("classify", "dedupe")
    graph.add_edge("dedupe", "build_proposal")
    graph.add_edge("build_proposal", END)
    return graph.compile()


def run_triage(
    reader: GitHubReadClient,
    classifier: Classifier,
    *,
    subject: str,
    requested_by: str,
) -> ProposalPayload:
    """Convenience wrapper: run the compiled graph and return the proposal."""
    app = build_graph(reader, classifier)
    final = app.invoke({"subject": subject, "requested_by": requested_by})
    return final["payload"]
