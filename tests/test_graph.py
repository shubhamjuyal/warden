"""The triage capability's LangGraph flow turns issues into a sound proposal."""
from warden_agent.capabilities.triage.graph import run_triage

from .fakes import SAMPLE_CLASSIFICATIONS, SAMPLE_ISSUES, FakeClassifier, FakeReader


def test_triage_produces_expected_actions():
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

    # Issue #2 is a duplicate of #1 -> exactly one close, on #2 (the newer one).
    closes = [a for a in payload.actions if a.type == "close"]
    assert len(closes) == 1
    assert closes[0].target == "2"
    assert closes[0].value == "1"

    # Issue #1 has an assignee -> one assign action.
    assigns = [a for a in payload.actions if a.type == "assign"]
    assert [a.value for a in assigns] == ["alice"]

    # Severity + area labels are always present per classified issue.
    labels_for_1 = {a.value for a in payload.actions if a.type == "label" and a.target == "1"}
    assert {"severity:critical", "area:auth", "bug"} <= labels_for_1


def test_dedupe_drops_self_or_unknown_duplicate_links():
    # Classification claims #3 duplicates a non-existent #99 -> dropped.
    from warden_agent.capabilities.triage.types import IssueClassification

    cls = [
        IssueClassification(issue_number=3, severity="low", area="docs", duplicate_of=99),
    ]
    payload = run_triage(
        FakeReader([SAMPLE_ISSUES[2]]),
        FakeClassifier(cls),
        subject="acme/api",
        requested_by="tester",
    )
    assert not [a for a in payload.actions if a.type == "close"]
