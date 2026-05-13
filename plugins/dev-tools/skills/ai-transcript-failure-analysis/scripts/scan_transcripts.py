#!/usr/bin/env python3
"""Scan Claude/Cursor JSONL transcripts for repo Harness failure candidates.

This script intentionally emits candidates, not final judgments. A human or
agent should validate each candidate with the evidence-chain standard from the
skill reference.
"""

from __future__ import annotations

import argparse
import collections
import difflib
import json
import os
import pathlib
import re
import sqlite3
import sys
from typing import Any, Dict, Iterable, List, Set, Tuple


STRONG_CORRECTIONS = [
    "不对",
    "错了",
    "改回去",
    "不是这个意思",
    "重新来",
    "不应该",
    "不能这样",
    "你理解错",
    "你搞错",
    "不符合",
    "撤回",
    "回退",
    "回滚",
    "wrong",
    "incorrect",
    "not what i meant",
]

WEAK_CORRECTIONS = [
    "不用",
    "不要",
    "换个方案",
    "这样不行",
    "有问题",
    "不需要",
    "先别",
    "别改",
    "没必要",
    "应该是",
    "你应该",
]

BUILD_COMMAND_HINTS = [
    "mvn",
    "gradle",
    "./gradlew",
    "npm test",
    "npm run",
    "yarn test",
    "pnpm test",
    "pytest",
    "go test",
    "cargo test",
    "tsc",
    "make test",
    "xcodebuild",
]

FAILURE_TEXT_HINTS = [
    "build failure",
    "compilation failure",
    "test failed",
    "tests failed",
    "failed",
    "error",
    "exception",
    "traceback",
    "报错",
    "失败",
    "错误",
    "异常",
    "找不到符号",
    "cannot find symbol",
    "could not resolve",
]

EDIT_TOOLS = {"Edit", "StrReplace", "ApplyPatch", "Write", "Delete"}
SHELL_TOOLS = {"Bash", "Shell"}


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


def message_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    message = obj.get("message")
    if isinstance(message, dict):
        return message
    if isinstance(obj, dict) and "role" in obj and ("content" in obj or "parts" in obj):
        return obj
    return {}


def content_blocks(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = message_dict(obj).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def role_of(obj: Dict[str, Any]) -> str:
    if obj.get("type") in {"user", "assistant", "system"}:
        return str(obj.get("type"))
    if obj.get("role") in {"user", "assistant", "system", "tool"}:
        return str(obj.get("role"))
    role = message_dict(obj).get("role")
    return str(role) if role else ""


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: List[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), (str, list)):
                    parts.append(text_from_content(block.get("content")))
    return "\n".join(part for part in parts if part)


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


def _strip_envelope(text: str) -> str:
    for tag in ENVELOPE_TAGS:
        text = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            " ",
            text,
            flags=re.S,
        )
    return text


_LEADING_FRONTMATTER_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n", re.MULTILINE)
_MANIFEST_KEY_RE = re.compile(
    r"^\s*(name|id|description|category|allowed-tools|argument-hint)\s*:",
    re.MULTILINE,
)


def _strip_leading_manifest_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block when it looks like a pasted
    slash-command / skill manifest (has `name:` / `description:` / etc.).

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


def real_user_text(obj: Dict[str, Any]) -> str:
    if role_of(obj) != "user":
        return ""

    blocks = content_blocks(obj)
    if blocks:
        if any(
            block.get("type") in ("tool_result", "tool-result") for block in blocks
        ):
            return ""
        text = "\n".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "text" and isinstance(block.get("text"), str)
        ).strip()
    else:
        content = message_dict(obj).get("content")
        text = content if isinstance(content, str) else ""

    generated_prefixes = (
        "The file ",
        "(Bash completed",
        "Exit code ",
        "Async agent launched successfully",
        "User has approved your plan",
    )
    if text.startswith(generated_prefixes):
        return ""
    if "<local-command-caveat>" in text or "<task-notification>" in text:
        return ""

    user_query_matches = re.findall(
        r"<user_query>(.*?)</user_query>", text, flags=re.S
    )
    if user_query_matches:
        text = "\n".join(match.strip() for match in user_query_matches)
    else:
        stripped = _strip_envelope(text)
        if not re.sub(r"\s+", "", stripped):
            return ""
        text = stripped.strip()
    text = _strip_leading_manifest_frontmatter(text).strip()
    return text


def tool_path(tool_name: str, tool_input: Any) -> List[str]:
    paths: List[str] = []
    if isinstance(tool_input, dict):
        for key in ("file_path", "path", "target_file", "relative_file_path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.append(value)
    elif isinstance(tool_input, str) and tool_name == "ApplyPatch":
        paths.extend(
            re.findall(r"\*\*\* (?:Update|Add|Delete) File: ([^\n]+)", tool_input)
        )
    return list(dict.fromkeys(paths))


def tool_command(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd")
        return command if isinstance(command, str) else ""
    return tool_input if isinstance(tool_input, str) else ""


def is_failure_result(text: str) -> bool:
    lower = (text or "").lower()
    if re.search(r"\berror\s+0\b", lower) and "build failure" not in lower:
        return False
    return any(hint in lower for hint in FAILURE_TEXT_HINTS)


def is_file_rollback_command(command: str) -> bool:
    return bool(
        re.search(
            r"(git\s+checkout\s+--\s+|git\s+restore\s+|git\s+reset\s+--hard|git\s+revert\b)",
            command or "",
        )
    )


def correction_search_text(text: str) -> str:
    """Remove common decision-request phrases that contain correction words."""
    text = text.lower()
    for phrase in ("对不对", "不对吗", "有没有不对", "不要符合我", "不要迎合我"):
        text = text.replace(phrase, " ")
    return text


def read_jsonl(path: pathlib.Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                try:
                    yield index, json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _pb_read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    shift = 0
    result = 0
    while True:
        if pos >= len(buf):
            raise IndexError("varint overrun")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _walk_blob_refs(buf: bytes, valid_ids: Set[str]) -> List[str]:
    """Return blob ids referenced anywhere in this protobuf blob, in document order.

    We don't have the schema, so we walk the wire format and pick up every
    length-delimited field whose payload is exactly 32 bytes and whose hex
    representation matches a known blob id. This is good enough to follow the
    Merkle-style child references that Cursor stores, without false positives
    on real text.
    """
    refs: List[str] = []
    seen: Set[str] = set()

    def walk(data: bytes) -> None:
        pos = 0
        while pos < len(data):
            try:
                tag, pos = _pb_read_varint(data, pos)
            except Exception:
                return
            wire_type = tag & 7
            if wire_type == 0:
                try:
                    _, pos = _pb_read_varint(data, pos)
                except Exception:
                    return
            elif wire_type == 1:
                pos += 8
            elif wire_type == 5:
                pos += 4
            elif wire_type == 2:
                try:
                    length, pos = _pb_read_varint(data, pos)
                except Exception:
                    return
                if length < 0 or pos + length > len(data):
                    return
                payload = data[pos:pos + length]
                pos += length
                if len(payload) == 32:
                    candidate = payload.hex()
                    if candidate in valid_ids and candidate not in seen:
                        seen.add(candidate)
                        refs.append(candidate)
                if len(payload) >= 2 and len(payload) != 32:
                    walk(payload)
            else:
                return

    walk(buf)
    return refs


def _extract_json_objects(buf: bytes) -> Iterable[Tuple[int, Any]]:
    """Yield (offset, parsed) for every balanced JSON object embedded in buf."""
    cursor = 0
    while True:
        start = buf.find(b'{"', cursor)
        if start < 0:
            return
        depth = 0
        in_string = False
        escape = False
        end = -1
        i = start
        while i < len(buf):
            byte = buf[i]
            if in_string:
                if escape:
                    escape = False
                elif byte == 0x5C:  # backslash
                    escape = True
                elif byte == 0x22:  # quote
                    in_string = False
            else:
                if byte == 0x22:
                    in_string = True
                elif byte == 0x7B:  # {
                    depth += 1
                elif byte == 0x7D:  # }
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            i += 1
        if end < 0:
            cursor = start + 1
            continue
        chunk = buf[start:end + 1]
        try:
            obj = json.loads(chunk.decode("utf-8"))
        except Exception:
            cursor = start + 1
            continue
        yield start, obj
        cursor = end + 1


def _looks_like_message(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("role") in {"user", "assistant", "system", "tool"}:
        return True
    if obj.get("type") in {"user", "assistant", "system", "tool"}:
        return True
    if isinstance(obj.get("message"), dict):
        return True
    return False


def read_store_db(path: pathlib.Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    """Read a Cursor `store.db` and yield message objects in chunk order.

    Cursor stores chat history in a content-addressed `blobs` table whose
    payload is protobuf, with full Vercel-AI-SDK-style JSON messages
    embedded as length-delimited string fields. We don't need the schema:
    we just pull every balanced JSON object out of every blob, ordered by
    the Merkle-ref walk from `meta.latestRootBlobId`, and dedupe by content.
    """
    try:
        con = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        print(f"[scan_transcripts] cannot open {path}: {exc}", file=sys.stderr)
        return
    try:
        con.row_factory = sqlite3.Row
        try:
            blob_rows = list(con.execute("SELECT id, data FROM blobs"))
        except sqlite3.Error as exc:
            print(
                f"[scan_transcripts] cannot read blobs from {path}: {exc}",
                file=sys.stderr,
            )
            return
        blobs: Dict[str, bytes] = {row["id"]: bytes(row["data"]) for row in blob_rows}
        if not blobs:
            print(f"[scan_transcripts] empty blobs table in {path}", file=sys.stderr)
            return

        roots: List[str] = []
        try:
            meta_rows = list(con.execute("SELECT key, value FROM meta"))
        except sqlite3.Error:
            meta_rows = []
        for row in meta_rows:
            value = row["value"]
            if not isinstance(value, str):
                continue
            try:
                decoded = bytes.fromhex(value).decode("utf-8")
            except Exception:
                continue
            try:
                meta_obj = json.loads(decoded)
            except Exception:
                continue
            if not isinstance(meta_obj, dict):
                continue
            for key in ("latestRootBlobId", "rootBlobId", "rootId"):
                rid = meta_obj.get(key)
                if isinstance(rid, str) and rid in blobs and rid not in roots:
                    roots.append(rid)
    finally:
        con.close()

    valid_ids = set(blobs.keys())
    if not roots:
        roots = sorted(valid_ids)

    ordered: List[str] = []
    visited: Set[str] = set()
    queue: List[str] = list(roots)
    while queue:
        current = queue.pop(0)
        if current in visited or current not in blobs:
            continue
        visited.add(current)
        ordered.append(current)
        for child in _walk_blob_refs(blobs[current], valid_ids):
            if child not in visited:
                queue.append(child)
    for bid in sorted(valid_ids):
        if bid not in visited:
            visited.add(bid)
            ordered.append(bid)

    seen_messages: Set[str] = set()
    index = 0
    for bid in ordered:
        for _, obj in _extract_json_objects(blobs[bid]):
            if not _looks_like_message(obj):
                continue
            try:
                fingerprint = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            except Exception:
                continue
            if fingerprint in seen_messages:
                continue
            seen_messages.add(fingerprint)
            yield index, obj
            index += 1


def analyze_events(
    events: Iterable[Tuple[int, Dict[str, Any]]],
    display_path: str,
) -> Dict[str, Any] | None:
    """Coarse-filter pass: produce candidate evidence, never final labels.

    The CLI's job is to surface "where the signal might be"—keyword hits,
    similarity hits, command-syntax hits, deterministic counts. Whether any
    of those constitute a correction, repeated instruction, or build/test
    failure loop is left to the agent reviewing the candidate. See §1.1 of
    the design doc.
    """
    user_texts: List[Tuple[int, str]] = []
    keyword_hits: List[Dict[str, Any]] = []
    edit_counts: collections.Counter[str] = collections.Counter()
    tool_uses: Dict[str, Tuple[str, Any, int]] = {}
    git_reverts: List[Dict[str, Any]] = []
    shell_failure_hits: List[Dict[str, Any]] = []
    last_action = -10_000
    last_action_brief: Tuple[str, int, str] | None = None
    tool_call_count = 0
    timestamps: List[str] = []

    def _recent_user_intent(at_index: int) -> str | None:
        for idx, text in reversed(user_texts):
            if idx <= at_index:
                return text
        return None

    for index, obj in events:
        if obj.get("timestamp"):
            timestamps.append(str(obj["timestamp"]))

        user_text = real_user_text(obj)
        if user_text:
            user_texts.append((index, user_text))
            lower = correction_search_text(user_text)
            strong_terms = [term for term in STRONG_CORRECTIONS if term.lower() in lower]
            weak_terms = [term for term in WEAK_CORRECTIONS if term.lower() in lower]
            if (strong_terms or weak_terms) and last_action >= 0 and index - last_action <= 25:
                keyword_hits.append({
                    "line": index,
                    "vocab": "strong" if strong_terms else "weak",
                    "terms": strong_terms + weak_terms,
                    "user_text": compact(user_text, 280),
                    "preceding_action_line": (
                        last_action_brief[1] if last_action_brief else None
                    ),
                    "preceding_action": (
                        last_action_brief[2] if last_action_brief else None
                    ),
                })

        for block in content_blocks(obj):
            block_type = block.get("type")
            if block_type in ("tool_use", "tool-call"):
                tool_name = block.get("name") or block.get("toolName") or ""
                tool_input = (
                    block.get("input")
                    if "input" in block
                    else block.get("args")
                )
                tool_id = (
                    block.get("id")
                    or block.get("tool_use_id")
                    or block.get("toolCallId")
                )
                tool_call_count += 1
                if tool_id:
                    tool_uses[str(tool_id)] = (str(tool_name), tool_input, index)

                if tool_name in EDIT_TOOLS:
                    paths = tool_path(str(tool_name), tool_input)
                    if not paths and tool_name == "ApplyPatch":
                        paths = ["<patch>"]
                    for file_path in paths:
                        edit_counts[file_path] += 1
                    last_action = index
                    brief_target = paths[0] if paths else "<unknown>"
                    last_action_brief = (
                        "edit",
                        index,
                        f"{tool_name} {compact(brief_target, 120)}",
                    )
                elif tool_name in SHELL_TOOLS:
                    command = tool_command(tool_input)
                    if is_file_rollback_command(command):
                        git_reverts.append({
                            "line": index,
                            "command": compact(command, 260),
                            "preceding_user_intent": compact(
                                _recent_user_intent(index) or "", 200
                            ) or None,
                        })
                    last_action = index
                    last_action_brief = (
                        "shell",
                        index,
                        f"{tool_name} {compact(command, 120)}",
                    )

            elif block_type in ("tool_result", "tool-result"):
                tool_id = block.get("tool_use_id") or block.get("toolCallId")
                if not tool_id or str(tool_id) not in tool_uses:
                    continue
                tool_name, tool_input, call_index = tool_uses[str(tool_id)]
                if tool_name not in SHELL_TOOLS:
                    continue
                result_payload = (
                    block.get("content")
                    if "content" in block
                    else block.get("result")
                )
                result_text = text_from_content(result_payload)
                lower_result = (result_text or "").lower()
                hit_terms = [term for term in FAILURE_TEXT_HINTS if term in lower_result]
                if (
                    "error" in hit_terms
                    and re.search(r"\berror\s+0\b", lower_result)
                    and "build failure" not in lower_result
                ):
                    hit_terms = [term for term in hit_terms if term != "error"]
                if hit_terms or block.get("is_error"):
                    command = tool_command(tool_input)
                    if any(hint in command.lower() for hint in BUILD_COMMAND_HINTS):
                        shell_failure_hits.append({
                            "line": call_index,
                            "command": compact(command, 220),
                            "result_keywords": hit_terms[:4],
                            "result_excerpt": compact(result_text, 260),
                        })

    similarity_hits: List[Dict[str, Any]] = []
    for (first_index, first_text), (second_index, second_text) in zip(
        user_texts, user_texts[1:]
    ):
        first_norm = normalize_text(first_text)
        second_norm = normalize_text(second_text)
        if min(len(first_norm), len(second_norm)) < 30:
            continue
        ratio = difflib.SequenceMatcher(
            None, first_norm[:1000], second_norm[:1000]
        ).ratio()
        exact_adjacent_duplicate = ratio == 1.0 and second_index - first_index <= 2
        if ratio >= 0.82 and not exact_adjacent_duplicate:
            similarity_hits.append({
                "first_line": first_index,
                "second_line": second_index,
                "similarity": round(ratio, 2),
                "first": compact(first_text, 220),
                "second": compact(second_text, 220),
            })

    strong_vocab_count = sum(1 for hit in keyword_hits if hit["vocab"] == "strong")
    weak_vocab_count = sum(1 for hit in keyword_hits if hit["vocab"] == "weak")
    repeated_edits = [(fp, c) for fp, c in edit_counts.items() if c >= 3]
    heavy_edits = [(fp, c) for fp, c in edit_counts.items() if c >= 5]

    score = 0.0
    hits: List[str] = []
    if similarity_hits:
        score += 0.8
        hits.append(f"similarity-hit:{len(similarity_hits)}")
    if git_reverts:
        score += 1.0 * len(git_reverts)
        hits.append(f"git-rollback:{len(git_reverts)}")
    if strong_vocab_count:
        score += 0.8 * strong_vocab_count
        hits.append(f"strong-vocab-hit:{strong_vocab_count}")
    if weak_vocab_count >= 2:
        score += 0.35 * weak_vocab_count
        hits.append(f"weak-vocab-hit:{weak_vocab_count}")
    if heavy_edits:
        score += 0.8
        hits.append(f"edit-count>=5:{len(heavy_edits)}")
    elif repeated_edits:
        score += 0.45
        hits.append(f"edit-count>=3:{len(repeated_edits)}")
    if len(shell_failure_hits) >= 3:
        score += 0.9
        hits.append(f"shell-failure-hit:{len(shell_failure_hits)}")
    elif shell_failure_hits:
        score += 0.3
        hits.append(f"shell-failure-hit:{len(shell_failure_hits)}")

    if score < 1.0:
        return None

    first_user = user_texts[0][1] if user_texts else ""
    return {
        "path": display_path,
        "score": round(score, 2),
        "hits": hits,
        "timestamps": [
            min(timestamps) if timestamps else "",
            max(timestamps) if timestamps else "",
        ],
        "real_user_messages": len(user_texts),
        "tool_calls": tool_call_count,
        "first_user": compact(first_user, 240),
        "keyword_hits": keyword_hits[:5],
        "similarity_hits": similarity_hits[:3],
        "edits": [
            {"file": compact(file_path, 180), "count": count}
            for file_path, count in sorted(repeated_edits, key=lambda item: -item[1])[:5]
        ],
        "git_reverts": git_reverts[:3],
        "shell_failure_hits": shell_failure_hits[:4],
    }


def _display_path(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _extract_metadata(display_path: str) -> Dict[str, str | None]:
    """Best-effort `user` / `workspace` extraction from transcript path.

    Used by the agent to aggregate candidates across users and workspaces.
    """
    user: str | None = None
    workspace: str | None = None

    match = re.search(r"ai-transcripts-([^-/]+)-\d{8}", display_path)
    if match:
        user = match.group(1)
    if not user:
        match = re.search(r"Users/([^/]+)/\.(?:claude|cursor)", display_path)
        if match:
            user = match.group(1)

    match = re.search(r"\.cursor/projects/([^/]+)/agent-transcripts", display_path)
    if match:
        workspace = match.group(1)
    if not workspace:
        match = re.search(r"\.claude/projects/([^/]+)/[^/]+\.jsonl", display_path)
        if match:
            workspace = match.group(1)
    if not workspace:
        match = re.search(r"\.cursor/chats/([^/]+)/", display_path)
        if match:
            workspace = f"cursor-chat:{match.group(1)[:12]}"

    return {"user": user, "workspace": workspace}


def _attach_metadata(
    candidate: Dict[str, Any] | None, display_path: str
) -> Dict[str, Any] | None:
    if candidate is None:
        return None
    candidate["metadata"] = _extract_metadata(display_path)
    return candidate


def analyze_jsonl_file(path: pathlib.Path, root: pathlib.Path) -> Dict[str, Any] | None:
    display = _display_path(path, root)
    return _attach_metadata(analyze_events(read_jsonl(path), display), display)


def analyze_store_db_file(path: pathlib.Path, root: pathlib.Path) -> Dict[str, Any] | None:
    display = _display_path(path, root)
    return _attach_metadata(analyze_events(read_store_db(path), display), display)


def render_markdown(
    candidates: List[Dict[str, Any]],
    roots: pathlib.Path | List[pathlib.Path],
) -> str:
    if isinstance(roots, pathlib.Path):
        roots = [roots]
    lines: List[str] = []
    lines.append("# Repo Harness Failure Candidate Scan")
    lines.append("")
    if len(roots) == 1:
        lines.append(f"Root: `{roots[0]}`")
    else:
        lines.append("Roots:")
        for root in roots:
            lines.append(f"- `{root}`")
    lines.append(f"Candidates: {len(candidates)}")
    lines.append("")
    lines.append(
        "> Coarse filter only. The scanner reports hint locations (keyword / similarity / "
        "command-syntax matches), never final labels. Read the raw excerpts and classify "
        "decision vs steer, correction strength, and failure-loop yourself."
    )
    lines.append("")

    for candidate in candidates:
        lines.append(f"## Score {candidate['score']} - `{candidate['path']}`")
        lines.append("")
        meta = candidate.get("metadata") or {}
        if meta.get("user") or meta.get("workspace"):
            lines.append(
                f"- User: {meta.get('user') or '?'} | Workspace: "
                f"{meta.get('workspace') or '?'}"
            )
        lines.append(f"- Hits: {', '.join(candidate['hits'])}")
        if any(candidate["timestamps"]):
            lines.append(
                f"- Time: {candidate['timestamps'][0]} .. {candidate['timestamps'][1]}"
            )
        lines.append(f"- Real user messages: {candidate['real_user_messages']}")
        lines.append(f"- Tool calls: {candidate['tool_calls']}")
        if candidate["first_user"]:
            lines.append(f"- Initial intent: {candidate['first_user']}")

        if candidate["keyword_hits"]:
            item = candidate["keyword_hits"][0]
            preceding = (
                f" after {item['preceding_action']} @line{item['preceding_action_line']}"
                if item.get("preceding_action")
                else ""
            )
            lines.append(
                f"- Keyword-hit sample (vocab={item['vocab']}, terms={item['terms']}, "
                f"line {item['line']}{preceding}): {item['user_text']}"
            )
        if candidate["similarity_hits"]:
            item = candidate["similarity_hits"][0]
            lines.append(
                f"- Similarity-hit sample: lines {item['first_line']}->{item['second_line']} "
                f"similarity={item['similarity']}"
            )
        if candidate["git_reverts"]:
            item = candidate["git_reverts"][0]
            intent = (
                f"  ↳ preceding user intent: {item['preceding_user_intent']}"
                if item.get("preceding_user_intent")
                else ""
            )
            lines.append(
                f"- File-rollback command: line {item['line']} `{item['command']}`"
            )
            if intent:
                lines.append(intent)
        if candidate["shell_failure_hits"]:
            item = candidate["shell_failure_hits"][0]
            lines.append(
                f"- Shell-failure-hit sample: line {item['line']} `{item['command']}` "
                f"keywords={item['result_keywords']}"
            )
        if candidate["edits"]:
            top_edit = candidate["edits"][0]
            lines.append(
                f"- Edit-count sample: {top_edit['count']}x `{top_edit['file']}`"
            )
        lines.append("")
        lines.append("Evidence-chain review (agent):")
        lines.append("- User intent (from raw excerpts, not from script labels):")
        lines.append("- Agent action:")
        lines.append("- Steer / decision classification:")
        lines.append("- Repo Harness gap:")
        lines.append("- Confidence:")
        lines.append("")

    return "\n".join(lines)


def _render_message(index: int, obj: Dict[str, Any], max_field: int = 1500) -> str:
    """Render one message into a human-readable block for the `show` command."""
    role = role_of(obj) or "?"
    out: List[str] = [f"[line={index}, role={role}]"]

    user_text = real_user_text(obj)
    if user_text:
        out.append(user_text[:max_field])
        return "\n".join(out)

    blocks = content_blocks(obj)
    if not blocks:
        content = message_dict(obj).get("content")
        if isinstance(content, str):
            out.append(content[:max_field])
        return "\n".join(out)

    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            if text:
                out.append(text[:max_field])
        elif block_type in ("tool_use", "tool-call"):
            name = block.get("name") or block.get("toolName") or ""
            tool_input = (
                block.get("input") if "input" in block else block.get("args")
            )
            target = ""
            if isinstance(tool_input, dict):
                for key in ("command", "file_path", "path", "target_file"):
                    val = tool_input.get(key)
                    if isinstance(val, str):
                        target = val
                        break
            elif isinstance(tool_input, str):
                target = tool_input
            out.append(f"  → tool_use {name}({compact(target, 240)})")
        elif block_type in ("tool_result", "tool-result"):
            payload = (
                block.get("content") if "content" in block else block.get("result")
            )
            text = text_from_content(payload)
            if text:
                out.append(f"  ← tool_result\n{compact(text, max_field)}")
            else:
                out.append("  ← tool_result (empty)")
    return "\n".join(out)


def show_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_transcripts.py show",
        description="Print a window of messages around a given line in a transcript.",
    )
    parser.add_argument("path", help="Transcript path (*.jsonl or store.db)")
    parser.add_argument(
        "--line", type=int, required=True,
        help="Center index (line for jsonl, virtual index for store.db)",
    )
    parser.add_argument(
        "--context", type=int, default=3,
        help="Number of messages before and after to include (default 3)",
    )
    args = parser.parse_args(argv)

    target = pathlib.Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"File not found: {target}", file=sys.stderr)
        return 2

    if target.suffix == ".jsonl":
        events: Iterable[Tuple[int, Dict[str, Any]]] = read_jsonl(target)
    elif target.name == "store.db":
        events = read_store_db(target)
    else:
        print(
            f"Unsupported file type (need *.jsonl or store.db): {target}",
            file=sys.stderr,
        )
        return 2

    lo = args.line - args.context
    hi = args.line + args.context

    print(f"# Window @ {target}")
    print(f"# Center line {args.line}, context ±{args.context}\n")

    seen = 0
    for index, obj in events:
        if index < lo:
            continue
        if index > hi:
            break
        block = _render_message(index, obj)
        print(block)
        print()
        seen += 1

    if seen == 0:
        print(
            f"(no messages found in window; transcript may have fewer than "
            f"{args.line + 1} messages)",
            file=sys.stderr,
        )
    return 0


def scan_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_transcripts.py [scan]", description=__doc__,
    )
    parser.add_argument(
        "roots",
        nargs="+",
        help="One or more transcript root directories",
    )
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument("--output", help="Write output to this file")
    args = parser.parse_args(argv)

    roots: List[pathlib.Path] = []
    for raw in args.roots:
        path = pathlib.Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"Root does not exist: {path}", file=sys.stderr)
            return 2
        roots.append(path)

    candidates: List[Dict[str, Any]] = []
    for root in roots:
        for path in root.rglob("*.jsonl"):
            candidate = analyze_jsonl_file(path, root)
            if candidate and candidate["score"] >= args.min_score:
                candidates.append(candidate)
        for path in root.rglob("store.db"):
            candidate = analyze_store_db_file(path, root)
            if candidate and candidate["score"] >= args.min_score:
                candidates.append(candidate)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    if args.limit > 0:
        candidates = candidates[: args.limit]

    roots_str = [str(root) for root in roots]
    if args.json:
        output = json.dumps(
            {"roots": roots_str, "candidates": candidates},
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = render_markdown(candidates, roots)

    if args.output:
        pathlib.Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def main(argv: List[str]) -> int:
    if argv and argv[0] == "show":
        return show_command(argv[1:])
    if argv and argv[0] == "scan":
        return scan_command(argv[1:])
    return scan_command(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
