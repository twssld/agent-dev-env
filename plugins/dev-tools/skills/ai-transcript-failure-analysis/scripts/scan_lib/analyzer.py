"""Coarse-filter analyzer.

Produces candidate evidence — never final labels. The CLI's job is to surface
"where the signal might be" (keyword hits, similarity hits, command-syntax
hits, deterministic counts). Whether any of those constitute a correction,
repeated instruction, or build/test failure loop is left to the agent reviewing
the candidate.
"""

from __future__ import annotations

import collections
import difflib
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from .config import AnalyzerConfig, EDIT_TOOLS, SHELL_TOOLS, Vocab
from .message import (
    content_blocks,
    is_file_rollback_command,
    looks_like_build_or_test_command,
    real_user_text,
    text_from_content,
    tool_command,
    tool_path,
)
from .text import compact, correction_search_text, normalize_text


def _is_failure_result_text(text: str, hints: Iterable[str]) -> List[str]:
    lower = (text or "").lower()
    hits = [term for term in hints if term in lower]
    if (
        "error" in hits
        and re.search(r"\berror\s+0\b", lower)
        and "build failure" not in lower
    ):
        hits = [term for term in hits if term != "error"]
    return hits


@dataclass
class _State:
    user_texts: List[Tuple[int, str]] = field(default_factory=list)
    keyword_hits: List[Dict[str, Any]] = field(default_factory=list)
    edit_counts: collections.Counter = field(default_factory=collections.Counter)
    tool_uses: Dict[str, Tuple[str, Any, int]] = field(default_factory=dict)
    git_reverts: List[Dict[str, Any]] = field(default_factory=list)
    shell_failure_hits: List[Dict[str, Any]] = field(default_factory=list)
    last_action: int = -10_000
    last_action_brief: Tuple[str, int, str] | None = None
    tool_call_count: int = 0
    timestamps: List[str] = field(default_factory=list)


def _recent_user_intent(state: _State, at_index: int) -> str | None:
    for idx, text in reversed(state.user_texts):
        if idx <= at_index:
            return text
    return None


def _ingest_user_message(
    state: _State,
    index: int,
    user_text: str,
    vocab: Vocab,
    cfg: AnalyzerConfig,
) -> None:
    state.user_texts.append((index, user_text))
    lower = correction_search_text(user_text, vocab.decision_request_phrases)
    strong_terms = [term for term in vocab.strong_corrections if term in lower]
    weak_terms = [term for term in vocab.weak_corrections if term in lower]
    if (
        (strong_terms or weak_terms)
        and state.last_action >= 0
        and index - state.last_action <= cfg.last_action_window
    ):
        state.keyword_hits.append({
            "line": index,
            "vocab": "strong" if strong_terms else "weak",
            "terms": strong_terms + weak_terms,
            "user_text": compact(user_text, 280),
            "preceding_action_line": (
                state.last_action_brief[1] if state.last_action_brief else None
            ),
            "preceding_action": (
                state.last_action_brief[2] if state.last_action_brief else None
            ),
        })


def _ingest_tool_use(state: _State, block: Dict[str, Any], index: int) -> None:
    tool_name = block.get("name") or block.get("toolName") or ""
    tool_input = block.get("input") if "input" in block else block.get("args")
    tool_id = (
        block.get("id")
        or block.get("tool_use_id")
        or block.get("toolCallId")
    )
    state.tool_call_count += 1
    if tool_id:
        state.tool_uses[str(tool_id)] = (str(tool_name), tool_input, index)

    if tool_name in EDIT_TOOLS:
        paths = tool_path(str(tool_name), tool_input)
        if not paths and tool_name == "ApplyPatch":
            paths = ["<patch>"]
        for file_path in paths:
            state.edit_counts[file_path] += 1
        state.last_action = index
        brief_target = paths[0] if paths else "<unknown>"
        state.last_action_brief = (
            "edit",
            index,
            f"{tool_name} {compact(brief_target, 120)}",
        )
    elif tool_name in SHELL_TOOLS:
        command = tool_command(tool_input)
        if is_file_rollback_command(command):
            state.git_reverts.append({
                "line": index,
                "command": compact(command, 260),
                "preceding_user_intent": compact(
                    _recent_user_intent(state, index) or "", 200
                ) or None,
            })
        state.last_action = index
        state.last_action_brief = (
            "shell",
            index,
            f"{tool_name} {compact(command, 120)}",
        )


def _ingest_tool_result(
    state: _State,
    block: Dict[str, Any],
    vocab: Vocab,
) -> None:
    tool_id = block.get("tool_use_id") or block.get("toolCallId")
    if not tool_id or str(tool_id) not in state.tool_uses:
        return
    tool_name, tool_input, call_index = state.tool_uses[str(tool_id)]
    if tool_name not in SHELL_TOOLS:
        return
    result_payload = (
        block.get("content") if "content" in block else block.get("result")
    )
    result_text = text_from_content(result_payload)
    hit_terms = _is_failure_result_text(result_text, vocab.failure_text_hints)
    if not hit_terms and not block.get("is_error"):
        return
    command = tool_command(tool_input)
    if not looks_like_build_or_test_command(command):
        return
    state.shell_failure_hits.append({
        "line": call_index,
        "command": compact(command, 220),
        "result_keywords": hit_terms[:4],
        "result_excerpt": compact(result_text, 260),
    })


def _collect_similarity_hits(
    user_texts: List[Tuple[int, str]], cfg: AnalyzerConfig
) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for (first_index, first_text), (second_index, second_text) in zip(
        user_texts, user_texts[1:]
    ):
        first_norm = normalize_text(first_text)
        second_norm = normalize_text(second_text)
        if min(len(first_norm), len(second_norm)) < cfg.similarity_min_chars:
            continue
        ratio = difflib.SequenceMatcher(
            None,
            first_norm[: cfg.similarity_compare_chars],
            second_norm[: cfg.similarity_compare_chars],
        ).ratio()
        exact_adjacent_duplicate = ratio == 1.0 and second_index - first_index <= 2
        if ratio >= cfg.similarity_threshold and not exact_adjacent_duplicate:
            hits.append({
                "first_line": first_index,
                "second_line": second_index,
                "similarity": round(ratio, 2),
                "first": compact(first_text, 220),
                "second": compact(second_text, 220),
            })
    return hits


def _score_candidate(
    state: _State,
    similarity_hits: List[Dict[str, Any]],
    cfg: AnalyzerConfig,
) -> Tuple[float, List[str], List[Tuple[str, int]], List[Tuple[str, int]]]:
    strong_vocab = sum(1 for hit in state.keyword_hits if hit["vocab"] == "strong")
    weak_vocab = sum(1 for hit in state.keyword_hits if hit["vocab"] == "weak")
    repeated_edits = [(fp, c) for fp, c in state.edit_counts.items() if c >= cfg.edit_count_repeated]
    heavy_edits = [(fp, c) for fp, c in state.edit_counts.items() if c >= cfg.edit_count_heavy]

    score = 0.0
    hits: List[str] = []
    if similarity_hits:
        score += cfg.similarity_score
        hits.append(f"similarity-hit:{len(similarity_hits)}")
    if state.git_reverts:
        score += cfg.git_revert_score * len(state.git_reverts)
        hits.append(f"git-rollback:{len(state.git_reverts)}")
    if strong_vocab:
        score += cfg.strong_vocab_score * strong_vocab
        hits.append(f"strong-vocab-hit:{strong_vocab}")
    if weak_vocab >= cfg.weak_vocab_min_count:
        score += cfg.weak_vocab_score * weak_vocab
        hits.append(f"weak-vocab-hit:{weak_vocab}")
    if heavy_edits:
        score += cfg.edit_heavy_score
        hits.append(f"edit-count>={cfg.edit_count_heavy}:{len(heavy_edits)}")
    elif repeated_edits:
        score += cfg.edit_repeated_score
        hits.append(f"edit-count>={cfg.edit_count_repeated}:{len(repeated_edits)}")
    if len(state.shell_failure_hits) >= cfg.shell_failure_burst:
        score += cfg.shell_failure_burst_score
        hits.append(f"shell-failure-hit:{len(state.shell_failure_hits)}")
    elif state.shell_failure_hits:
        score += cfg.shell_failure_score
        hits.append(f"shell-failure-hit:{len(state.shell_failure_hits)}")

    return round(score, 2), hits, repeated_edits, heavy_edits


def analyze_events(
    events: Iterable[Tuple[int, Dict[str, Any]]],
    display_path: str,
    *,
    vocab: Vocab,
    cfg: AnalyzerConfig,
    min_score: float | None = None,
) -> Dict[str, Any] | None:
    state = _State()
    for index, obj in events:
        if obj.get("timestamp"):
            state.timestamps.append(str(obj["timestamp"]))

        user_text = real_user_text(obj)
        if user_text:
            _ingest_user_message(state, index, user_text, vocab, cfg)

        for block in content_blocks(obj):
            block_type = block.get("type")
            if block_type in ("tool_use", "tool-call"):
                _ingest_tool_use(state, block, index)
            elif block_type in ("tool_result", "tool-result"):
                _ingest_tool_result(state, block, vocab)

    similarity_hits = _collect_similarity_hits(state.user_texts, cfg)
    score, hits, repeated_edits, _heavy = _score_candidate(state, similarity_hits, cfg)

    cutoff = cfg.score_floor if min_score is None else min_score
    if score < cutoff:
        return None

    first_user = state.user_texts[0][1] if state.user_texts else ""
    return {
        "path": display_path,
        "score": score,
        "hits": hits,
        "timestamps": [
            min(state.timestamps) if state.timestamps else "",
            max(state.timestamps) if state.timestamps else "",
        ],
        "real_user_messages": len(state.user_texts),
        "tool_calls": state.tool_call_count,
        "first_user": compact(first_user, 240),
        "keyword_hits": state.keyword_hits[:5],
        "similarity_hits": similarity_hits[:3],
        "edits": [
            {"file": compact(file_path, 180), "count": count}
            for file_path, count in sorted(repeated_edits, key=lambda item: -item[1])[:5]
        ],
        "git_reverts": state.git_reverts[:3],
        "shell_failure_hits": state.shell_failure_hits[:4],
    }


def display_path(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


_USER_FROM_AI_TX = re.compile(r"ai-transcripts-([^-/]+)-\d{8}")
_USER_FROM_HOME = re.compile(r"Users/([^/]+)/\.(?:claude|cursor)")
_WS_FROM_CURSOR_PROJ = re.compile(r"\.cursor/projects/([^/]+)/agent-transcripts")
_WS_FROM_CLAUDE_PROJ = re.compile(r"\.claude/projects/([^/]+)/[^/]+\.jsonl")
_WS_FROM_CURSOR_CHATS = re.compile(r"\.cursor/chats/([^/]+)/")


def extract_metadata(display: str) -> Dict[str, str | None]:
    """Best-effort `user` / `workspace` extraction from transcript path."""
    user: str | None = None
    workspace: str | None = None
    match = _USER_FROM_AI_TX.search(display)
    if match:
        user = match.group(1)
    if not user:
        match = _USER_FROM_HOME.search(display)
        if match:
            user = match.group(1)
    match = _WS_FROM_CURSOR_PROJ.search(display)
    if match:
        workspace = match.group(1)
    if not workspace:
        match = _WS_FROM_CLAUDE_PROJ.search(display)
        if match:
            workspace = match.group(1)
    if not workspace:
        match = _WS_FROM_CURSOR_CHATS.search(display)
        if match:
            workspace = f"cursor-chat:{match.group(1)[:12]}"
    return {"user": user, "workspace": workspace}


def attach_metadata(
    candidate: Dict[str, Any] | None, display: str
) -> Dict[str, Any] | None:
    if candidate is None:
        return None
    candidate["metadata"] = extract_metadata(display)
    return candidate
