import textwrap

import unittest

from commands.create import CloudInitOptions, _compose_user_data, _validate_public_key


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


class ValidatePublicKeyTests(unittest.TestCase):
    """Tests for SSH public key validation."""

    def test_accepts_valid_ssh_rsa_key(self) -> None:
        # Real SSH RSA key
        valid_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDKXiMW/IJRupbViIkQ0PducYAtk7gHUvebBvP+yMcSOYEOdV6GVlJBTYprmcnRaVxsq1g7hBNtUyf2Ymv49eAP70fdYxmNeN4IyURJGItHE9QLAWXttNPUnDMHanb8PtQIY+u/I9BogLSi7LH4tLDq+LUh71/0TZAlb7R6v8RQ4admzFa43WAck48iuEED9HiDWJdUd4IrjcOUgskLTysHdS2Y84+odnkJgOCCZEh3YCvksqsQ9UXodm6VSoJb/qoauEAvuoOXxjxzjsCeyd00tpvCh/ZU6bP439Y07C24z+RYRjgceKDy0wEn0Ge+eZb+hTCcmSo5+p249iZyBl+/ user@host"
        self.assertTrue(_validate_public_key(valid_key))

    def test_accepts_valid_ssh_ed25519_key(self) -> None:
        # Real SSH Ed25519 key
        valid_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEiiaEGZ7bz2o4R7Ki/JWsdpAr5+m2eiGLsWOq+ckigZ user@host"
        self.assertTrue(_validate_public_key(valid_key))

    def test_accepts_valid_ecdsa_key(self) -> None:
        # Real ECDSA key
        valid_key = "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBOJcUO7YUs88scff0GA1RYDd+Dr8UKl9tThGKy5GTbH8H4bfpqxsP4+8fvjL6LXsTC/oCyFxZk+imWl3ve9zvfI= user@host"
        self.assertTrue(_validate_public_key(valid_key))

    def test_accepts_key_without_comment(self) -> None:
        # Key without optional comment part
        valid_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEiiaEGZ7bz2o4R7Ki/JWsdpAr5+m2eiGLsWOq+ckigZ"
        self.assertTrue(_validate_public_key(valid_key))

    def test_rejects_empty_string(self) -> None:
        self.assertFalse(_validate_public_key(""))

    def test_rejects_whitespace_only(self) -> None:
        self.assertFalse(_validate_public_key("   "))

    def test_rejects_none(self) -> None:
        self.assertFalse(_validate_public_key(None))

    def test_rejects_single_part(self) -> None:
        self.assertFalse(_validate_public_key("ssh-rsa"))

    def test_rejects_invalid_key_type(self) -> None:
        invalid_key = "invalid-type AAAAB3NzaC1yc2EAAAADAQABAAABAQDKXiMW user@host"
        self.assertFalse(_validate_public_key(invalid_key))

    def test_rejects_invalid_base64(self) -> None:
        # Invalid base64 characters
        invalid_key = "ssh-rsa INVALID!@#BASE64 user@host"
        self.assertFalse(_validate_public_key(invalid_key))

    def test_rejects_malformed_base64(self) -> None:
        # Incomplete base64 padding
        invalid_key = "ssh-rsa AAA user@host"
        self.assertFalse(_validate_public_key(invalid_key))

    def test_accepts_security_keys(self) -> None:
        # Hardware security key types (using valid base64 from a real ed25519 key)
        sk_key = "sk-ssh-ed25519@openssh.com AAAAC3NzaC1lZDI1NTE5AAAAIEiiaEGZ7bz2o4R7Ki/JWsdpAr5+m2eiGLsWOq+ckigZ user@host"
        self.assertTrue(_validate_public_key(sk_key))


if __name__ == "__main__":
    unittest.main()
