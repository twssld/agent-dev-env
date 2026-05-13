"""Tunable knobs and lexicon loading.

All thresholds, window sizes, and word lists live here so users can adjust
behavior without editing analyzer code. Lexicons are loaded from
`references/vocab.json`.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import List


DEFAULT_VOCAB_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "references"
    / "vocab.json"
)


@dataclass(frozen=True)
class Vocab:
    strong_corrections: List[str]
    weak_corrections: List[str]
    build_command_hints: List[str]
    failure_text_hints: List[str]
    decision_request_phrases: List[str]


def load_vocab(path: pathlib.Path | None = None) -> Vocab:
    target = path or DEFAULT_VOCAB_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    return Vocab(
        strong_corrections=[s.lower() for s in data["strong_corrections"]],
        weak_corrections=[s.lower() for s in data["weak_corrections"]],
        build_command_hints=[s.lower() for s in data["build_command_hints"]],
        failure_text_hints=[s.lower() for s in data["failure_text_hints"]],
        decision_request_phrases=[s.lower() for s in data["decision_request_phrases"]],
    )


@dataclass(frozen=True)
class AnalyzerConfig:
    """Numeric knobs for the analyzer.

    Defaults match the original heuristic shipped with the skill. CLI flags
    override individual fields when needed.
    """

    last_action_window: int = 25
    similarity_threshold: float = 0.82
    similarity_min_chars: int = 30
    similarity_compare_chars: int = 1000
    edit_count_repeated: int = 3
    edit_count_heavy: int = 5
    shell_failure_burst: int = 3
    score_floor: float = 1.0
    compact_default: int = 180
    show_max_field: int = 1500

    similarity_score: float = 0.8
    git_revert_score: float = 1.0
    strong_vocab_score: float = 0.8
    weak_vocab_score: float = 0.35
    weak_vocab_min_count: int = 2
    edit_heavy_score: float = 0.8
    edit_repeated_score: float = 0.45
    shell_failure_burst_score: float = 0.9
    shell_failure_score: float = 0.3


EDIT_TOOLS = frozenset({"Edit", "StrReplace", "ApplyPatch", "Write", "Delete"})
SHELL_TOOLS = frozenset({"Bash", "Shell"})

ENVELOPE_TAGS = (
    "user_info",
    "git_status",
    "agent_transcripts",
    "rules",
    "open_and_recently_viewed_files",
    "attached_files",
    "system_notification",
    "system_reminder",
    "system-reminder",
    "agent_skills",
    "available_skills",
    "command-message",
    "command-name",
    "additional_data",
    "hooks_context",
    "hooks-context",
)

GENERATED_USER_PREFIXES = (
    "The file ",
    "(Bash completed",
    "Exit code ",
    "Async agent launched successfully",
    "User has approved your plan",
)
