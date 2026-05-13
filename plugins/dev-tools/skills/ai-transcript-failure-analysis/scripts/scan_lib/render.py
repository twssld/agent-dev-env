"""Markdown and `show`-window rendering."""

from __future__ import annotations

import pathlib
from typing import Any, Dict, Iterable, List, Tuple

from .message import (
    content_blocks,
    message_dict,
    real_user_text,
    role_of,
    text_from_content,
)
from .text import compact


def _format_keyword_hit(item: Dict[str, Any]) -> str:
    preceding = (
        f" after {item['preceding_action']} @line{item['preceding_action_line']}"
        if item.get("preceding_action")
        else ""
    )
    return (
        f"  - line {item['line']} (vocab={item['vocab']}, terms={item['terms']}"
        f"{preceding}): {item['user_text']}"
    )


def _format_similarity_hit(item: Dict[str, Any]) -> str:
    return (
        f"  - lines {item['first_line']}->{item['second_line']} "
        f"similarity={item['similarity']}"
    )


def _format_git_revert(item: Dict[str, Any]) -> str:
    intent = item.get("preceding_user_intent")
    suffix = f"  ↳ preceding intent: {intent}" if intent else ""
    line = f"  - line {item['line']} `{item['command']}`"
    return f"{line}\n{suffix}" if suffix else line


def _format_shell_failure(item: Dict[str, Any]) -> str:
    return (
        f"  - line {item['line']} `{item['command']}` "
        f"keywords={item['result_keywords']}"
    )


def _format_edit(item: Dict[str, Any]) -> str:
    return f"  - {item['count']}x `{item['file']}`"


def render_markdown(
    candidates: List[Dict[str, Any]],
    roots: pathlib.Path | List[pathlib.Path],
    *,
    top_n: int = 3,
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
        "> Coarse filter only. The scanner reports hint locations (keyword / "
        "similarity / command-syntax matches), never final labels. Read the raw "
        "excerpts and classify decision vs steer, correction strength, and "
        "failure-loop yourself."
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

        sections: List[Tuple[str, List[str]]] = [
            (
                "Keyword hits",
                [_format_keyword_hit(item) for item in candidate["keyword_hits"][:top_n]],
            ),
            (
                "Similarity hits",
                [_format_similarity_hit(item) for item in candidate["similarity_hits"][:top_n]],
            ),
            (
                "File rollback commands",
                [_format_git_revert(item) for item in candidate["git_reverts"][:top_n]],
            ),
            (
                "Shell failure hits",
                [_format_shell_failure(item) for item in candidate["shell_failure_hits"][:top_n]],
            ),
            (
                "Edit hot-spots",
                [_format_edit(item) for item in candidate["edits"][:top_n]],
            ),
        ]
        for title, body in sections:
            if not body:
                continue
            lines.append(f"- {title}:")
            lines.extend(body)

        lines.append("")
        lines.append("Evidence-chain review (agent):")
        lines.append("- User intent (from raw excerpts, not from script labels):")
        lines.append("- Agent action:")
        lines.append("- Steer / decision classification:")
        lines.append("- Repo Harness gap:")
        lines.append("- Confidence:")
        lines.append("")

    return "\n".join(lines)


def render_message(index: int, obj: Dict[str, Any], max_field: int = 1500) -> str:
    """Render one message into a human-readable block for `show`."""
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
