"""JSONL transcript reader."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple


@dataclass
class JsonlStats:
    lines_read: int = 0
    json_decode_errors: int = 0
    open_errors: int = 0


def read_jsonl(
    path: pathlib.Path, stats: JsonlStats | None = None
) -> Iterable[Tuple[int, Dict[str, Any]]]:
    if stats is None:
        stats = JsonlStats()
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        stats.open_errors += 1
        return
    try:
        for index, line in enumerate(handle):
            stats.lines_read += 1
            try:
                yield index, json.loads(line)
            except json.JSONDecodeError:
                stats.json_decode_errors += 1
                continue
    finally:
        handle.close()
