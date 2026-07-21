"""Measured model-routing and context-trimming optimization primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import Settings
from app.schemas.api import ConversationMessage
from app.schemas.common import OptimizationMode

_COMPLEX_SIGNALS = re.compile(
    r"(?i)\b(stopped|shutdown|overload|fault|alarm|diagnos|root cause|unsafe|"
    r"conflict|multiple|intermittent|create|work order)\b"
)

# History relevance is deliberately lexical and deterministic.  It is a context-budgeting
# heuristic only; matched text is still untrusted conversation content when sent to the model.
_PROVENANCE_MARKER = re.compile(r"\[conversation:(?:turn|item)-\d+\]", re.IGNORECASE)
_MACHINE_ID = re.compile(
    r"(?<![A-Za-z0-9_])(?=[A-Za-z0-9_-]{2,32}(?![A-Za-z0-9_]))"
    r"(?=[A-Za-z0-9_-]*[0-9])[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*"
    r"(?![A-Za-z0-9_])"
)
_MAINTENANCE_SIGNAL = re.compile(
    r"(?i)\b(?:alarms?|faults?|trips?|tripped|overloads?|symptoms?|stopp?ed|"
    r"stalls?|shutdown|intermittent|abnormal|vibrat(?:e|es|ed|ing|ion)|noise|"
    r"noisy|squeal|heat|hot|temperature|pressure|leaks?|smoke|burn(?:ing|t)?|"
    r"unsafe|hazards?|interlocks?|guards?|lockout|tagout|loto|energized|"
    r"electrical|injur(?:y|ed)|emergency|failures?|failed)\b"
)
_LEXICAL_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")
_LEXICAL_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "also",
        "and",
        "are",
        "before",
        "but",
        "can",
        "could",
        "diagnose",
        "for",
        "from",
        "has",
        "have",
        "into",
        "machine",
        "maintenance",
        "not",
        "please",
        "that",
        "the",
        "then",
        "this",
        "was",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
    }
)
_RECENT_CONTEXT_MESSAGES = 4


@dataclass(frozen=True, slots=True)
class RouteDecision:
    model: str
    reason: str


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def select(self, message: str, mode: OptimizationMode) -> RouteDecision:
        if self.settings.llm_provider == "demo":
            return RouteDecision(self.settings.demo_model, "offline demo provider selected")
        if mode == OptimizationMode.BASELINE:
            return RouteDecision(self.settings.default_model, "baseline disables model routing")
        word_count = len(message.split())
        if word_count <= 35 and not _COMPLEX_SIGNALS.search(message):
            return RouteDecision(
                self.settings.small_model,
                "short, low-complexity request routed to configured lower-cost model",
            )
        return RouteDecision(
            self.settings.default_model,
            "diagnostic complexity signal requires configured default model",
        )


@dataclass(frozen=True, slots=True)
class TrimmedHistory:
    messages: list[ConversationMessage]
    omitted_messages: int
    omitted_characters: int


def trim_history(
    history: list[ConversationMessage],
    settings: Settings,
    mode: OptimizationMode,
    *,
    current_message: str = "",
) -> TrimmedHistory:
    if mode == OptimizationMode.BASELINE:
        return TrimmedHistory(list(history), 0, 0)

    message_limit = settings.history_message_limit
    character_limit = settings.history_character_limit
    current_terms = _meaningful_terms(current_message)
    current_machine_ids = _machine_ids(current_message)
    recent_start = max(0, len(history) - min(_RECENT_CONTEXT_MESSAGES, message_limit))

    candidates: list[tuple[tuple[int, int, int], int, ConversationMessage]] = []
    for index, message in enumerate(history):
        relevance = _relevance_score(message.content, current_terms, current_machine_ids)
        if index == len(history) - 1:
            # Preserve the newest turn whenever it fits, even when it is a short acknowledgement.
            priority = (3, relevance, index)
        elif relevance:
            # Relevant older context beats generic recent padding.
            priority = (2, relevance, index)
        elif index >= recent_start:
            priority = (1, 0, index)
        else:
            continue
        candidates.append((priority, index, message))

    selected_by_index: dict[int, ConversationMessage] = {}
    selected_chars = 0
    for _, index, message in sorted(candidates, key=lambda item: item[0], reverse=True):
        content_length = len(message.content)
        if len(selected_by_index) == message_limit:
            break
        if selected_chars + content_length > character_limit:
            continue
        selected_by_index[index] = message
        selected_chars += content_length

    selected = [selected_by_index[index] for index in sorted(selected_by_index)]
    omitted = len(history) - len(selected_by_index)
    all_chars = sum(len(message.content) for message in history)
    return TrimmedHistory(
        messages=selected,
        omitted_messages=omitted,
        omitted_characters=max(0, all_chars - selected_chars),
    )


def _relevance_score(
    content: str,
    current_terms: set[str],
    current_machine_ids: set[str],
) -> int:
    content_machine_ids = _machine_ids(content)
    exact_machine_matches = content_machine_ids & current_machine_ids
    signal_count = len({match.casefold() for match in _MAINTENANCE_SIGNAL.findall(content)})
    lexical_overlap = _meaningful_terms(content) & current_terms
    return (
        (12 * len(exact_machine_matches))
        + (6 if content_machine_ids else 0)
        + (4 * min(signal_count, 3))
        + (2 * min(len(lexical_overlap), 5))
    )


def _machine_ids(text: str) -> set[str]:
    without_markers = _PROVENANCE_MARKER.sub(" ", text)
    return {match.group(0).casefold() for match in _MACHINE_ID.finditer(without_markers)}


def _meaningful_terms(text: str) -> set[str]:
    without_markers = _PROVENANCE_MARKER.sub(" ", text)
    return {
        token
        for raw_token in _LEXICAL_TOKEN.findall(without_markers)
        if len(token := raw_token.casefold()) >= 3 and token not in _LEXICAL_STOP_WORDS
    }
