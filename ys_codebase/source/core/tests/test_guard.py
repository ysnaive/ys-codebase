"""
Unit tests for Core Security Gatekeeper SDK (core.guard).
Covers authorized dispatch, unauthorized bypass rejection, and testing mode exemption.
"""

import os
import sys
import unittest
from unittest.mock import patch
from io import StringIO

from dev.testing.case import YSCBTestCase
from core.guard import (
    guard_dispatch,
    GUARD_ENV_TOKEN,
    GUARD_ENV_HOST,
    GUARD_ENV_TESTING,
)


class TestGuardSDK(YSCBTestCase):
    def setUp(self):
        self._orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_guard_authorized(self):
        """FT-01: When both token and host dir are present, guard_dispatch passes silently."""
        os.environ[GUARD_ENV_HOST] = "/mock/workspace"
        os.environ[GUARD_ENV_TOKEN] = "valid_token_123"
        os.environ.pop(GUARD_ENV_TESTING, None)

        try:
            guard_dispatch("test-mod")
        except SystemExit:
            self.fail("guard_dispatch raised SystemExit unexpectedly on authorized dispatch.")
        self.mark_passed()

    def test_guard_unauthorized_exit(self):
        """FT-02: When token or host dir is missing, guard_dispatch prints guidance and exits with 126."""
        os.environ.pop(GUARD_ENV_TOKEN, None)
        os.environ.pop(GUARD_ENV_HOST, None)
        os.environ.pop(GUARD_ENV_TESTING, None)

        err_stream = StringIO()
        with patch.object(sys, "stderr", err_stream):
            with self.assertRaises(SystemExit) as cm:
                guard_dispatch("knowledge-db")
            self.assertEqual(cm.exception.code, 126)

        err_output = err_stream.getvalue()
        self.assertIn("[YSCB Security Guard]", err_output)
        self.assertIn("knowledge-db", err_output)
        self.assertIn("python yscb.py knowledge-db", err_output)
        self.mark_passed()

    def test_guard_testing_mode(self):
        """FT-03: When YSCB_TESTING is 1, guard_dispatch exempts validation."""
        os.environ.pop(GUARD_ENV_TOKEN, None)
        os.environ.pop(GUARD_ENV_HOST, None)
        os.environ[GUARD_ENV_TESTING] = "1"

        try:
            guard_dispatch("any-module")
        except SystemExit:
            self.fail("guard_dispatch raised SystemExit unexpectedly in testing mode.")
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
