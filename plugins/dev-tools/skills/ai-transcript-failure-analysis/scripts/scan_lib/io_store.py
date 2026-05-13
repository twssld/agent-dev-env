"""Cursor `store.db` reader.

Cursor stores chat history in a content-addressed `blobs` table whose payload
is protobuf, with full Vercel-AI-SDK-style JSON messages embedded as
length-delimited string fields. We don't need the schema: we walk the wire
format to follow Merkle-style child references between blobs, and pull every
balanced JSON object out of every blob, ordered by the Merkle walk from
`meta.latestRootBlobId`.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Set, Tuple


@dataclass
class StoreStats:
    blobs_total: int = 0
    blobs_walked: int = 0
    blobs_unparseable: int = 0
    json_objects_seen: int = 0
    messages_yielded: int = 0
    messages_deduped: int = 0
    open_errors: int = 0


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


def _walk_blob_refs(buf: bytes, valid_ids: Set[str]) -> Tuple[List[str], bool]:
    """Return (blob ids referenced anywhere in this protobuf blob, ok?).

    `ok` is False if we hit an unrecoverable wire-format error mid-walk; the
    list still contains anything we found before the error so the caller can
    decide whether to keep going. We pick up every length-delimited field
    whose payload is exactly 32 bytes and whose hex matches a known blob id.
    """
    refs: List[str] = []
    seen: Set[str] = set()
    ok = True

    def walk(data: bytes) -> bool:
        pos = 0
        while pos < len(data):
            try:
                tag, pos = _pb_read_varint(data, pos)
            except Exception:
                return False
            wire_type = tag & 7
            if wire_type == 0:
                try:
                    _, pos = _pb_read_varint(data, pos)
                except Exception:
                    return False
            elif wire_type == 1:
                pos += 8
            elif wire_type == 5:
                pos += 4
            elif wire_type == 2:
                try:
                    length, pos = _pb_read_varint(data, pos)
                except Exception:
                    return False
                if length < 0 or pos + length > len(data):
                    return False
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
                return False
        return True

    ok = walk(buf)
    return refs, ok


def _extract_json_objects(buf: bytes) -> Iterable[Tuple[int, Any]]:
    """Yield (offset, parsed) for every balanced JSON object embedded in buf.

    Anchors on `{` followed by an optional run of whitespace and a `"`. Cursor's
    real payloads are tightly packed (`{"`) but accepting `{ "` keeps us
    forward-compatible against minor format tweaks.
    """
    cursor = 0
    n = len(buf)
    while True:
        start = buf.find(b"{", cursor)
        if start < 0:
            return
        scan = start + 1
        while scan < n and buf[scan] in (0x20, 0x09, 0x0A, 0x0D):
            scan += 1
        if scan >= n or buf[scan] != 0x22:
            cursor = start + 1
            continue
        depth = 0
        in_string = False
        escape = False
        end = -1
        i = start
        while i < n:
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


def _ordered_blob_ids(
    blobs: Dict[str, bytes],
    roots: List[str],
    stats: StoreStats,
) -> List[str]:
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
        children, ok = _walk_blob_refs(blobs[current], valid_ids)
        if not ok:
            stats.blobs_unparseable += 1
        for child in children:
            if child not in visited:
                queue.append(child)
    for bid in sorted(valid_ids):
        if bid not in visited:
            visited.add(bid)
            ordered.append(bid)
    return ordered


def _read_meta_roots(con: sqlite3.Connection, valid_ids: Set[str]) -> List[str]:
    roots: List[str] = []
    try:
        meta_rows = list(con.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return roots
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
            if isinstance(rid, str) and rid in valid_ids and rid not in roots:
                roots.append(rid)
    return roots


def read_store_db(
    path: pathlib.Path,
    stats: StoreStats | None = None,
    *,
    log: bool = True,
) -> Iterable[Tuple[int, Dict[str, Any]]]:
    if stats is None:
        stats = StoreStats()
    try:
        con = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        stats.open_errors += 1
        if log:
            print(f"[scan_transcripts] cannot open {path}: {exc}", file=sys.stderr)
        return
    try:
        con.row_factory = sqlite3.Row
        try:
            blob_rows = list(con.execute("SELECT id, data FROM blobs"))
        except sqlite3.Error as exc:
            if log:
                print(
                    f"[scan_transcripts] cannot read blobs from {path}: {exc}",
                    file=sys.stderr,
                )
            return
        blobs: Dict[str, bytes] = {row["id"]: bytes(row["data"]) for row in blob_rows}
        stats.blobs_total = len(blobs)
        if not blobs:
            if log:
                print(f"[scan_transcripts] empty blobs table in {path}", file=sys.stderr)
            return
        roots = _read_meta_roots(con, set(blobs.keys()))
    finally:
        con.close()

    ordered = _ordered_blob_ids(blobs, roots, stats)

    seen_messages: Set[str] = set()
    index = 0
    for bid in ordered:
        stats.blobs_walked += 1
        for _, obj in _extract_json_objects(blobs[bid]):
            stats.json_objects_seen += 1
            if not _looks_like_message(obj):
                continue
            try:
                fingerprint = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            except Exception:
                continue
            if fingerprint in seen_messages:
                stats.messages_deduped += 1
                continue
            seen_messages.add(fingerprint)
            stats.messages_yielded += 1
            yield index, obj
            index += 1
