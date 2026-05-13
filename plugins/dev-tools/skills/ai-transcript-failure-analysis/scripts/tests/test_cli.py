import io
import json
import pathlib
import unittest
from contextlib import redirect_stderr, redirect_stdout

from scan_lib.cli import main


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _run(argv):
    out = io.StringIO()
    err = io.StringIO()
    rc_holder = {"rc": None}
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc_holder["rc"] = main(argv)
    except SystemExit as exc:
        rc_holder["rc"] = exc.code
    return rc_holder["rc"], out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_scan_implicit_subcommand_runs_and_emits_markdown(self):
        rc, stdout, _ = _run([str(FIXTURES.parent / "fixtures")])
        self.assertEqual(rc, 0)
        self.assertIn("Repo Harness Failure Candidate Scan", stdout)
        self.assertIn("sample.jsonl", stdout)

    def test_scan_json_emits_top_n_evidence(self):
        rc, stdout, _ = _run(["scan", str(FIXTURES), "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["candidates"])
        cand = payload["candidates"][0]
        self.assertIn("keyword_hits", cand)
        self.assertIn("git_reverts", cand)

    def test_scan_min_score_filters_everything(self):
        rc, stdout, _ = _run(
            ["scan", str(FIXTURES), "--json", "--min-score", "99"]
        )
        self.assertEqual(rc, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["candidates"], [])

    def test_show_runs_against_jsonl(self):
        rc, stdout, _ = _run([
            "show",
            str(FIXTURES / "sample.jsonl"),
            "--line", "3",
            "--context", "1",
        ])
        self.assertEqual(rc, 0)
        self.assertTrue("[line=2" in stdout or "[line=3" in stdout)
        self.assertIn("你又改错了", stdout)

    def test_help_does_not_crash(self):
        rc, stdout, _ = _run(["--help"])
        self.assertIn(rc, (0, None))
        self.assertIn("scan_transcripts.py", stdout)

    def test_directory_named_scan_does_not_collide(self):
        """Regression for the old string-routing CLI: a real path called
        `scan` used to be eaten as the subcommand."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_root = pathlib.Path(tmp) / "scan"
            fake_root.mkdir()
            rc, stdout, _ = _run([str(fake_root)])
            self.assertEqual(rc, 0)
            self.assertIn("Candidates: 0", stdout)


if __name__ == "__main__":
    unittest.main()
