import dataclasses
import pathlib
import unittest

from scan_lib.analyzer import analyze_events, extract_metadata
from scan_lib.config import AnalyzerConfig, load_vocab
from scan_lib.io_jsonl import read_jsonl


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class AnalyzerTest(unittest.TestCase):
    def test_analyze_events_finds_steer_pattern(self):
        vocab = load_vocab()
        cfg = AnalyzerConfig()
        events = read_jsonl(FIXTURES / "sample.jsonl")
        candidate = analyze_events(events, "sample.jsonl", vocab=vocab, cfg=cfg)
        self.assertIsNotNone(candidate)
        hits_set = " ".join(candidate["hits"])
        self.assertIn("strong-vocab-hit", hits_set)
        self.assertIn("git-rollback", hits_set)
        self.assertIn("edit-count", hits_set)
        self.assertGreaterEqual(candidate["score"], cfg.score_floor)

    def test_min_score_can_filter_out(self):
        vocab = load_vocab()
        cfg = dataclasses.replace(AnalyzerConfig(), score_floor=99.0)
        events = read_jsonl(FIXTURES / "sample.jsonl")
        candidate = analyze_events(events, "sample.jsonl", vocab=vocab, cfg=cfg)
        self.assertIsNone(candidate)

    def test_min_score_can_be_lowered_below_default_floor(self):
        """Regression: original code hard-coded score < 1.0; --min-score < 1
        should now actually surface lower-scoring candidates."""
        vocab = load_vocab()
        cfg = dataclasses.replace(AnalyzerConfig(), score_floor=0.1)
        events = [
            (0, {"type": "user", "message": {"role": "user", "content": "run tests"}}),
            (
                1,
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "x1",
                                "name": "Bash",
                                "input": {"command": "pytest"},
                            }
                        ],
                    },
                },
            ),
            (
                2,
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "x1",
                                "content": "FAILED something error",
                            }
                        ],
                    },
                },
            ),
        ]
        candidate = analyze_events(events, "synthetic", vocab=vocab, cfg=cfg)
        self.assertIsNotNone(candidate)
        self.assertLess(candidate["score"], 1.0)
        self.assertTrue(any("shell-failure-hit" in h for h in candidate["hits"]))

    def test_extract_metadata_user_and_workspace(self):
        meta = extract_metadata(".claude/projects/some-project/abc123.jsonl")
        self.assertEqual(meta["workspace"], "some-project")
        meta2 = extract_metadata(".cursor/projects/proj/agent-transcripts/x.jsonl")
        self.assertEqual(meta2["workspace"], "proj")
        meta3 = extract_metadata("ai-transcripts-alice-20260401/foo.jsonl")
        self.assertEqual(meta3["user"], "alice")


if __name__ == "__main__":
    unittest.main()
