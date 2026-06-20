"""The LangGraph flow turns issues into a sound proposal."""
from warden_agent.graph import run_triage
from warden_common.schemas import ActionType

from .fakes import SAMPLE_CLASSIFICATIONS, SAMPLE_ISSUES, FakeClassifier, FakeReader


def test_triage_produces_expected_actions():
    payload = run_triage(
        FakeReader(SAMPLE_ISSUES),
        FakeClassifier(SAMPLE_CLASSIFICATIONS),
        repo="acme/api",
        requested_by="tester",
    )
    assert payload.repo == "acme/api"

    # Issue #2 is a duplicate of #1 -> exactly one close, on #2 (the newer one).
    closes = [a for a in payload.actions if a.type == ActionType.CLOSE]
    assert len(closes) == 1
    assert closes[0].issue_number == 2
    assert closes[0].value == "1"

    # Issue #1 has an assignee -> one assign action.
    assigns = [a for a in payload.actions if a.type == ActionType.ASSIGN]
    assert [a.value for a in assigns] == ["alice"]

    # Severity + area labels are always present per classified issue.
    labels_for_1 = {a.value for a in payload.actions if a.type == ActionType.LABEL and a.issue_number == 1}
    assert {"severity:critical", "area:auth", "bug"} <= labels_for_1


def test_dedupe_drops_self_or_unknown_duplicate_links():
    # Classification claims #3 duplicates a non-existent #99 -> dropped.
    from warden_common.schemas import IssueClassification

    cls = [
        IssueClassification(issue_number=3, severity="low", area="docs", duplicate_of=99),
    ]
    payload = run_triage(
        FakeReader([SAMPLE_ISSUES[2]]),
        FakeClassifier(cls),
        repo="acme/api",
        requested_by="tester",
    )
    assert not [a for a in payload.actions if a.type == ActionType.CLOSE]
