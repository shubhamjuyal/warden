"""GitHub-style **bold** is rewritten to Slack's single-asterisk *bold*."""
from __future__ import annotations

from warden_agent.surfaces.mrkdwn import to_slack_mrkdwn


def test_double_asterisk_bold_becomes_single():
    assert to_slack_mrkdwn("1. **#2**: Add BSE support") == "1. *#2*: Add BSE support"


def test_multiple_bold_spans_on_one_line():
    out = to_slack_mrkdwn("**#1** is a *bug* and **#2** an enhancement")
    assert out == "*#1* is a *bug* and *#2* an enhancement"


def test_plain_text_untouched():
    assert to_slack_mrkdwn("shubhamjuyal/stonks has 2 open issues") == (
        "shubhamjuyal/stonks has 2 open issues"
    )


def test_lone_double_asterisk_left_alone():
    # No closing pair -> not bold; must not be mangled.
    assert to_slack_mrkdwn("pass it as **kwargs to the func") == (
        "pass it as **kwargs to the func"
    )


def test_code_spans_are_protected():
    # ** inside inline code or fences must survive verbatim.
    assert to_slack_mrkdwn("use `**kwargs` here") == "use `**kwargs` here"
    assert to_slack_mrkdwn("```\nf(**opts)\n```") == "```\nf(**opts)\n```"
    # ...but bold outside the code span is still converted.
    assert to_slack_mrkdwn("**note** `**kwargs`") == "*note* `**kwargs`"
