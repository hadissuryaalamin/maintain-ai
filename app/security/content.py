"""Prompt-injection boundary helpers for retrieved content."""

from __future__ import annotations

import re

UNTRUSTED_START = "<untrusted_retrieved_content>"
UNTRUSTED_END = "</untrusted_retrieved_content>"

_LIKELY_INJECTION = re.compile(
    r"(?i)(ignore\s+(all|any|the)?\s*(previous|prior|system)|"
    r"export\s+all|reveal\s+(the\s+)?(secret|credential|prompt)|"
    r"grant\s+(me\s+)?permission|execute\s+this\s+(command|tool))"
)


def delimit_untrusted_content(content: str) -> str:
    """Make the trust boundary visible to the model and logs."""

    escaped = content.replace(UNTRUSTED_START, "[removed delimiter]").replace(
        UNTRUSTED_END, "[removed delimiter]"
    )
    return f"{UNTRUSTED_START}\n{escaped}\n{UNTRUSTED_END}"


def contains_likely_prompt_injection(content: str) -> bool:
    """Detection is telemetry/defense-in-depth, never an authorization decision."""

    return bool(_LIKELY_INJECTION.search(content))
