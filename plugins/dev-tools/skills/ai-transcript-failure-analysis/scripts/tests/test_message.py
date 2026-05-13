import unittest

from scan_lib.message import (
    is_file_rollback_command,
    looks_like_build_or_test_command,
    real_user_text,
    role_of,
    tool_command,
    tool_path,
)


class MessageHelpersTest(unittest.TestCase):
    def test_real_user_text_skips_tool_results(self):
        obj = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
                ],
            },
        }
        self.assertEqual(real_user_text(obj), "")

    def test_real_user_text_extracts_envelope_stripped_text(self):
        obj = {
            "type": "user",
            "message": {
                "role": "user",
                "content": "<system-reminder>noise</system-reminder>真实意图",
            },
        }
        self.assertEqual(real_user_text(obj), "真实意图")

    def test_real_user_text_returns_empty_for_caveat_envelope(self):
        obj = {
            "type": "user",
            "message": {
                "role": "user",
                "content": "<local-command-caveat>cmd</local-command-caveat>",
            },
        }
        self.assertEqual(real_user_text(obj), "")

    def test_role_of_handles_top_level_type_and_nested_role(self):
        self.assertEqual(role_of({"type": "assistant"}), "assistant")
        self.assertEqual(
            role_of({"message": {"role": "user", "content": "x"}}), "user"
        )

    def test_tool_path_picks_known_keys(self):
        self.assertEqual(tool_path("Edit", {"file_path": "a.ts"}), ["a.ts"])
        self.assertEqual(tool_path("Edit", {"target_file": "b.ts"}), ["b.ts"])

    def test_tool_path_apply_patch_extracts_from_string(self):
        patch = "*** Update File: a.ts\n*** Add File: b.ts\n"
        self.assertEqual(tool_path("ApplyPatch", patch), ["a.ts", "b.ts"])

    def test_tool_command_handles_dict_or_string(self):
        self.assertEqual(tool_command({"command": "ls"}), "ls")
        self.assertEqual(tool_command({"cmd": "ls"}), "ls")
        self.assertEqual(tool_command("npm test"), "npm test")
        self.assertEqual(tool_command(None), "")

    def test_is_file_rollback_command_matches_known_forms(self):
        self.assertTrue(is_file_rollback_command("git checkout -- src/a.ts"))
        self.assertTrue(is_file_rollback_command("git restore src/a.ts"))
        self.assertTrue(is_file_rollback_command("git reset --hard HEAD~1"))
        self.assertTrue(is_file_rollback_command("git revert HEAD"))
        self.assertFalse(is_file_rollback_command("git checkout main"))

    def test_looks_like_build_or_test_command_excludes_npm_run_dev(self):
        self.assertTrue(looks_like_build_or_test_command("pytest tests/"))
        self.assertTrue(looks_like_build_or_test_command("npm test"))
        self.assertTrue(looks_like_build_or_test_command("npm run test"))
        self.assertTrue(looks_like_build_or_test_command("yarn test"))
        self.assertTrue(looks_like_build_or_test_command("go test ./..."))
        self.assertFalse(looks_like_build_or_test_command("npm run dev"))
        self.assertFalse(looks_like_build_or_test_command("npm run start"))


if __name__ == "__main__":
    unittest.main()
