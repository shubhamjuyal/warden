"""The LangGraph triage flow.

    fetch → classify → build_proposal

``fetch`` reads the open issues and the repo's assignable collaborators; the
classifier picks one label (and maybe an assignee) per issue; ``build_proposal``
turns that into the generic proposal. Each node is a pure-ish step over a shared
state dict. The GitHub reader and the classifier are injected, so the same graph
runs against live GitHub + OpenAI in production and against fakes in tests —
without changing the flow.
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
    assignees: list[str]  # repo collaborators that can be assigned
    classifications: list[IssueClassification]
    payload: ProposalPayload


def build_graph(reader: GitHubReadClient, classifier: Classifier):
    def fetch(state: TriageState) -> TriageState:
        issues = reader.list_open_issues(state["subject"])
        assignees = reader.list_assignees(state["subject"])
        return {
            "issues": [i.to_prompt_dict() for i in issues],
            "assignees": assignees,
        }

    def classify(state: TriageState) -> TriageState:
        items = classifier.classify(
            state["subject"], state.get("issues", []), state.get("assignees", [])
        )
        return {"classifications": items}

    def make_proposal(state: TriageState) -> TriageState:
        payload = build_payload(
            state["subject"],
            state.get("classifications", []),
            state.get("assignees", []),
        )
        return {"payload": payload}

    graph = StateGraph(TriageState)
    graph.add_node("fetch", fetch)
    graph.add_node("classify", classify)
    graph.add_node("build_proposal", make_proposal)

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "classify")
    graph.add_edge("classify", "build_proposal")
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
