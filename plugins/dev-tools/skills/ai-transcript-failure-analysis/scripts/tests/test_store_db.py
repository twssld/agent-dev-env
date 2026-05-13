"""Minimum smoke test for the Cursor `store.db` reader.

We don't have access to a real Cursor proto schema, so we build the simplest
possible blob that should still be parseable: a single length-delimited string
field whose payload is a JSON message object. The reader's job is to find any
balanced JSON inside a blob, regardless of surrounding wire-format noise."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import tempfile
import unittest

from scan_lib.io_store import StoreStats, _extract_json_objects, read_store_db


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        if n < 0x80:
            out.append(n)
            return bytes(out)
        out.append((n & 0x7F) | 0x80)
        n >>= 7


def _length_delimited_field(field_number: int, payload: bytes) -> bytes:
    tag = (field_number << 3) | 2
    return _varint(tag) + _varint(len(payload)) + payload


def _make_blob(msg_json: str) -> bytes:
    return _length_delimited_field(1, msg_json.encode("utf-8"))


class StoreDbReaderTest(unittest.TestCase):
    def test_extract_json_objects_finds_embedded_message(self):
        msg = json.dumps({"role": "user", "content": "hello"})
        blob = b"\x00\x00" + _make_blob(msg) + b"\x00"
        objs = list(_extract_json_objects(blob))
        self.assertEqual(len(objs), 1)
        _, parsed = objs[0]
        self.assertEqual(parsed["content"], "hello")

    def test_read_store_db_yields_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "store.db"
            con = sqlite3.connect(str(db))
            try:
                con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
                con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                m1 = json.dumps({"role": "user", "content": "first"})
                m2 = json.dumps({"role": "assistant", "content": "second"})
                con.execute(
                    "INSERT INTO blobs (id, data) VALUES (?, ?)",
                    ("00" * 32, _make_blob(m1)),
                )
                con.execute(
                    "INSERT INTO blobs (id, data) VALUES (?, ?)",
                    ("11" * 32, _make_blob(m2)),
                )
                con.commit()
            finally:
                con.close()

            stats = StoreStats()
            messages = list(read_store_db(db, stats, log=False))
            self.assertEqual(len(messages), 2)
            self.assertEqual(stats.blobs_total, 2)
            self.assertGreaterEqual(stats.blobs_walked, 2)
            roles = sorted(obj.get("role") for _, obj in messages)
            self.assertEqual(roles, ["assistant", "user"])

    def test_read_store_db_dedupes_identical_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "store.db"
            con = sqlite3.connect(str(db))
            try:
                con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
                con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                msg = json.dumps({"role": "user", "content": "dup"})
                con.execute(
                    "INSERT INTO blobs (id, data) VALUES (?, ?)",
                    ("aa" * 32, _make_blob(msg)),
                )
                con.execute(
                    "INSERT INTO blobs (id, data) VALUES (?, ?)",
                    ("bb" * 32, _make_blob(msg)),
                )
                con.commit()
            finally:
                con.close()

            stats = StoreStats()
            messages = list(read_store_db(db, stats, log=False))
            self.assertEqual(len(messages), 1)
            self.assertEqual(stats.messages_deduped, 1)


if __name__ == "__main__":
    unittest.main()
