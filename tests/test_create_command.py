import textwrap

import unittest

from commands.create import CloudInitOptions, _compose_user_data


class ComposeUserDataTests(unittest.TestCase):
    def test_returns_original_content_when_no_key(self) -> None:
        options = CloudInitOptions(
            enabled=True,
            path=None,
            runtime="shell",
            content="#!/bin/bash\necho 'hello'\n",
        )

        result = _compose_user_data(options, None)

        self.assertEqual(options.content, result)

    def test_injects_authorized_key_script(self) -> None:
        options = CloudInitOptions(enabled=False, path=None, runtime=None, content=None)

        result = _compose_user_data(options, "ssh-ed25519 AAAEXAMPLE")

        self.assertIsNotNone(result)
        result_text = result or ""
        self.assertIn("authorized_keys", result_text)
        self.assertIn("ssh-ed25519 AAAEXAMPLE", result_text)
        self.assertTrue(result_text.startswith("#!/bin/bash"))

    def test_appends_shell_script_after_key_injection(self) -> None:
        options = CloudInitOptions(
            enabled=True,
            path=None,
            runtime="shell",
            content="#!/bin/bash\necho shell\n",
        )

        result = _compose_user_data(options, "ssh-rsa AAAANOTHER")

        self.assertIsNotNone(result)
        result_text = result or ""
        self.assertIn("ssh-rsa AAAANOTHER", result_text)
        self.assertIn("echo shell", result_text.splitlines()[-1])

    def test_drops_leading_shebang_from_shell_script(self) -> None:
        options = CloudInitOptions(
            enabled=True,
            path=None,
            runtime="shell",
            content="#!/usr/bin/env bash\necho hi\n",
        )

        result = _compose_user_data(options, "ssh-ed25519 AAAATEST")

        self.assertIsNotNone(result)
        result_text = result or ""
        self.assertNotIn("#!/usr/bin/env bash", result_text)
        self.assertIn("echo hi", result_text)

    def test_wraps_python_script_execution(self) -> None:
        python_script = textwrap.dedent(
            """#!/usr/bin/env python3
print('hi')
"""
        )
        options = CloudInitOptions(
            enabled=True,
            path=None,
            runtime="python",
            content=python_script,
        )

        result = _compose_user_data(options, "ssh-ed25519 AAAPYTHON")

        self.assertIsNotNone(result)
        result_text = result or ""
        self.assertIn("cat <<'PYCODE' >/tmp/ephetzner_user_script.py", result_text)
        self.assertIn("python3 /tmp/ephetzner_user_script.py", result_text)
        self.assertIn("ssh-ed25519 AAAPYTHON", result_text)


if __name__ == "__main__":
    unittest.main()
