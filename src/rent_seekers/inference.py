"""Mechanical language limits for observational analytical outputs."""

from __future__ import annotations

import re
from typing import Literal

InferenceClass = Literal["descriptive_only"]

_CAUSAL_PATTERNS = (
    re.compile(r"\bcaused? by\b", re.IGNORECASE),
    re.compile(r"\bcaus(?:e|es|ed)\b", re.IGNORECASE),
    re.compile(r"\bleads? to\b", re.IGNORECASE),
    re.compile(r"\bresults? in\b", re.IGNORECASE),
    re.compile(r"\bdue to\b", re.IGNORECASE),
    re.compile(r"\bthe effect of\b", re.IGNORECASE),
    re.compile(r"\bthe impact of\b", re.IGNORECASE),
)
_LIMITING_LANGUAGE = (
    "not evidence",
    "not a cause",
    "not caused",
    "does not show",
    "does not establish",
    "cannot conclude",
    "cannot attribute",
    "no causal",
)


def validate_inference_language(
    text: str,
    *,
    inference_class: InferenceClass,
) -> str:
    """Reject unqualified causal wording for a descriptive-only result."""
    if inference_class != "descriptive_only":
        raise ValueError(f"unsupported inference class: {inference_class}")
    for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", text):
        lowered = sentence.lower()
        if any(pattern.search(sentence) for pattern in _CAUSAL_PATTERNS) and not any(
            limit in lowered for limit in _LIMITING_LANGUAGE
        ):
            raise ValueError(
                "descriptive_only language cannot assert a causal explanation: "
                f"{sentence.strip()}"
            )
    return text
