"""The triage capability's LangGraph flow turns issues into a sound proposal."""
from warden_agent.capabilities.triage.graph import run_triage
from warden_agent.capabilities.triage.types import IssueClassification

from .fakes import SAMPLE_CLASSIFICATIONS, SAMPLE_ISSUES, FakeClassifier, FakeReader


def test_triage_proposes_one_label_per_issue_plus_assignees():
    payload = run_triage(
        FakeReader(SAMPLE_ISSUES),
        FakeClassifier(SAMPLE_CLASSIFICATIONS),
        subject="acme/api",
        requested_by="tester",
    )
    assert payload.capability == "triage"
    assert payload.subject == "acme/api"
    # Every action targets the github_issues provider.
    assert {a.provider for a in payload.actions} == {"github_issues"}

    # Exactly one label per classified issue, each from the standard set.
    labels = [a for a in payload.actions if a.type == "label"]
    assert {a.target: a.value for a in labels} == {
        "1": "bug",
        "2": "duplicate",
        "3": "documentation",
    }

    # Only issue #1 had a clear assignee.
    assigns = [a for a in payload.actions if a.type == "assign"]
    assert [(a.target, a.value) for a in assigns] == [("1", "alice")]

    # Triage no longer closes or emits severity/area labels.
    assert not [a for a in payload.actions if a.type == "close"]


def test_assignee_not_in_collaborators_is_dropped():
    # The model named someone who can't be assigned -> the assign action is dropped,
    # but the label still stands.
    cls = [IssueClassification(issue_number=3, label="documentation", assignee="ghost")]
    payload = run_triage(
        FakeReader([SAMPLE_ISSUES[2]], assignees=["alice"]),
        FakeClassifier(cls),
        subject="acme/api",
        requested_by="tester",
    )
    assert not [a for a in payload.actions if a.type == "assign"]
    assert [a.value for a in payload.actions if a.type == "label"] == ["documentation"]
