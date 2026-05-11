from __future__ import annotations

import math
import re
from collections import Counter

from .models import Tool

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "i",
    "in",
    "into",
    "is",
    "it",
    "make",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "with",
}


def select_tools(prompt: str, tools: list[Tool], limit: int = 5) -> list[Tool]:
    if limit <= 0:
        raise ValueError("limit must be greater than zero.")
    if len(tools) <= limit:
        return tools

    prompt_terms = _tokens(prompt)
    if not prompt_terms:
        return tools[:limit]

    document_terms = [_tokens(tool.searchable_text) for tool in tools]
    document_frequency = Counter(term for terms in document_terms for term in set(terms))

    scored = []
    for index, (tool, terms) in enumerate(zip(tools, document_terms)):
        score = _score(prompt_terms, terms, document_frequency, len(tools))
        scored.append((score, -index, tool))

    scored.sort(reverse=True)
    return [tool for score, _, tool in scored[:limit] if score > 0] or tools[:limit]


def _score(
    prompt_terms: list[str],
    tool_terms: list[str],
    document_frequency: Counter[str],
    document_count: int,
) -> float:
    prompt_counts = Counter(prompt_terms)
    tool_counts = Counter(tool_terms)
    score = 0.0

    for term, prompt_count in prompt_counts.items():
        if term not in tool_counts:
            continue
        inverse_document_frequency = math.log((1 + document_count) / (1 + document_frequency[term])) + 1
        score += prompt_count * tool_counts[term] * inverse_document_frequency

    score += _substring_bonus(prompt_terms, tool_terms)
    return score


def _substring_bonus(prompt_terms: list[str], tool_terms: list[str]) -> float:
    joined_prompt = " ".join(prompt_terms)
    bonus = 0.0
    for term in set(tool_terms):
        if len(term) >= 4 and term in joined_prompt:
            bonus += 0.2
    return bonus


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in TOKEN_RE.findall(text.lower().replace("_", " ").replace("-", " "))
        if token not in STOP_WORDS
    ]
