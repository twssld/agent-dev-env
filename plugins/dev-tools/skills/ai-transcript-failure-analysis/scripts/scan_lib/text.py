"""Text utilities: compaction, normalization, envelope stripping."""

from __future__ import annotations

import re
from typing import Iterable

from .config import ENVELOPE_TAGS


def compact(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def normalize_text(text: str) -> str:
    text = re.sub(r"<timestamp>.*?</timestamp>", " ", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _build_envelope_pattern(tags: Iterable[str]) -> re.Pattern[str]:
    """Anchored envelope matcher.

    We require the opening tag to sit at the very start of the message or to
    follow whitespace/newline. That avoids stripping the tag if a user message
    *quotes* `<system-reminder>` mid-sentence (a real risk when discussing
    Claude Code prompts themselves).
    """
    joined = "|".join(re.escape(tag) for tag in tags)
    return re.compile(
        rf"(?:^|\s)<({joined})\b[^>]*>.*?</\1>",
        re.S,
    )


_ENVELOPE_RE = _build_envelope_pattern(ENVELOPE_TAGS)


def strip_envelope(text: str) -> str:
    return _ENVELOPE_RE.sub(" ", text or "")


_LEADING_FRONTMATTER_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n", re.MULTILINE)
_MANIFEST_KEY_RE = re.compile(
    r"^\s*(name|id|description|category|allowed-tools|argument-hint)\s*:",
    re.MULTILINE,
)


def strip_leading_manifest_frontmatter(text: str) -> str:
    """Strip a YAML frontmatter block when it looks like a pasted manifest.

    Plain markdown horizontal rules at the top of a real user message are NOT
    stripped — only blocks whose content carries manifest-style keys.
    """
    leading_ws = len(text) - len(text.lstrip())
    body = text[leading_ws:]
    if not body.startswith("---"):
        return text
    match = _LEADING_FRONTMATTER_RE.match(body)
    if not match:
        return text
    if not _MANIFEST_KEY_RE.search(match.group(1)):
        return text
    return text[leading_ws + match.end():]


def correction_search_text(text: str, decision_request_phrases: Iterable[str]) -> str:
    """Remove decision-request phrases that contain correction-vocab terms.

    Avoids false-positive steers when the user is asking for honest feedback
    ("对不对", "不要迎合我") rather than correcting the agent.
    """
    text = text.lower()
    for phrase in decision_request_phrases:
        text = text.replace(phrase, " ")
    return text
