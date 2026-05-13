"""Message-shape helpers shared by IO and analysis layers."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .config import GENERATED_USER_PREFIXES
from .text import strip_envelope, strip_leading_manifest_frontmatter


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

    if text.startswith(GENERATED_USER_PREFIXES):
        return ""
    if "<local-command-caveat>" in text or "<task-notification>" in text:
        return ""

    user_query_matches = re.findall(
        r"<user_query>(.*?)</user_query>", text, flags=re.S
    )
    if user_query_matches:
        text = "\n".join(match.strip() for match in user_query_matches)
    else:
        stripped = strip_envelope(text)
        if not re.sub(r"\s+", "", stripped):
            return ""
        text = stripped.strip()
    text = strip_leading_manifest_frontmatter(text).strip()
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


_FILE_ROLLBACK_RE = re.compile(
    r"(git\s+checkout\s+--\s+|git\s+restore\s+|git\s+reset\s+--hard|git\s+revert\b)"
)


def is_file_rollback_command(command: str) -> bool:
    return bool(_FILE_ROLLBACK_RE.search(command or ""))


_BUILD_TEST_HINT_RE = re.compile(
    r"(?:\bnpm\s+(?:test|run\s+(?:test|tests|check|lint|typecheck|build))\b"
    r"|\byarn\s+(?:test|run\s+(?:test|tests|check|lint|typecheck|build))\b"
    r"|\bpnpm\s+(?:test|run\s+(?:test|tests|check|lint|typecheck|build))\b"
    r"|\bpytest\b|\bgo\s+test\b|\bcargo\s+test\b|\bmake\s+test\b"
    r"|\bmvn\b|\bgradle\b|\./gradlew\b|\btsc\b|\bxcodebuild\b)"
)


def looks_like_build_or_test_command(command: str) -> bool:
    """Tighter than substring matching: avoids `npm run dev` / `npm run start`
    being treated as a test/build command.
    """
    return bool(_BUILD_TEST_HINT_RE.search((command or "").lower()))
