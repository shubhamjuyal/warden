"""Normalize the model's Markdown to Slack's mrkdwn.

LLMs habitually emit GitHub-flavoured Markdown — most visibly ``**bold**`` — but
Slack's mrkdwn uses a SINGLE asterisk for bold, so ``**#2**`` renders as literal
asterisks in the thread. We fix it deterministically on the way out (the prompt
asks for the right syntax, but the model slips), converting paired ``**bold**`` to
``*bold*`` while leaving code spans untouched so things like ``**kwargs`` or
``2**8`` inside backticks survive.
"""
from __future__ import annotations

import re

# Paired **bold** only — a lone ** (e.g. **kwargs) has no closing pair and is left
# alone. Non-greedy, and requires non-space at the edges so "** "/" **" don't match.
_BOLD = re.compile(r"\*\*(\S(?:.*?\S)?)\*\*", re.DOTALL)

# Split out fenced ```blocks``` and inline `code` so we never rewrite inside them.
_CODE = re.compile(r"(```.*?```|`[^`]*`)", re.DOTALL)


def to_slack_mrkdwn(text: str) -> str:
    if not text or "**" not in text:
        return text
    parts = _CODE.split(text)
    # split() with a capturing group keeps the delimiters; code spans start with `.
    return "".join(
        part if part.startswith("`") else _BOLD.sub(r"*\1*", part) for part in parts
    )
