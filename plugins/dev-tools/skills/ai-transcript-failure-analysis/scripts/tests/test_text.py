import unittest

from scan_lib.text import (
    compact,
    correction_search_text,
    normalize_text,
    strip_envelope,
    strip_leading_manifest_frontmatter,
)


class TextHelpersTest(unittest.TestCase):
    def test_compact_collapses_whitespace_and_truncates(self):
        out = compact("a   b\nc " * 100, limit=20)
        self.assertEqual(len(out), 20)
        self.assertTrue(out.endswith("..."))
        self.assertNotIn("  ", out)

    def test_strip_envelope_removes_known_block(self):
        text = "<system-reminder>noise</system-reminder>real"
        self.assertEqual(strip_envelope(text).strip(), "real")

    def test_strip_envelope_anchored_does_not_remove_quoted_tag_mid_sentence(self):
        text = "I asked Claude what `<system-reminder>` does and got a weird answer"
        out = strip_envelope(text)
        self.assertIn("<system-reminder>", out)

    def test_strip_envelope_anchored_removes_after_newline(self):
        text = "user words\n<system-reminder>foo</system-reminder>more words"
        out = strip_envelope(text)
        self.assertNotIn("<system-reminder>", out)
        self.assertIn("user words", out)
        self.assertIn("more words", out)

    def test_strip_leading_manifest_frontmatter_strips_when_keys_present(self):
        text = "---\nname: foo\ndescription: bar\n---\nbody"
        self.assertEqual(strip_leading_manifest_frontmatter(text).strip(), "body")

    def test_strip_leading_manifest_frontmatter_keeps_plain_hr(self):
        text = "---\njust a horizontal rule above some prose\n"
        self.assertEqual(strip_leading_manifest_frontmatter(text), text)

    def test_normalize_text_strips_xml_and_lowercases(self):
        self.assertEqual(
            normalize_text("Hello <b>WORLD</b><timestamp>x</timestamp>"),
            "hello world",
        )

    def test_correction_search_text_removes_decision_request_phrases(self):
        out = correction_search_text(
            "你说这样对不对，不要迎合我",
            decision_request_phrases=["对不对", "不要迎合我"],
        )
        self.assertNotIn("对不对", out)
        self.assertNotIn("不要迎合我", out)


if __name__ == "__main__":
    unittest.main()
