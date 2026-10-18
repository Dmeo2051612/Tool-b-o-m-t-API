import importlib.util
from pathlib import Path
import unittest
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "test_finora_user_isolation.py"
SPEC = importlib.util.spec_from_file_location("isolation_module", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IsolationPolicyTests(unittest.TestCase):
    def test_shared_id_fails(self):
        status, _ = MODULE.evaluate_ids({"1", "2"}, {"2", "3"}, True)
        self.assertEqual(status, "FAIL")

    def test_separate_data_both_sides_passes(self):
        status, _ = MODULE.evaluate_ids({"1"}, {"2"}, True)
        self.assertEqual(status, "PASS")

    def test_data_only_on_a_is_limited_pass(self):
        status, message = MODULE.evaluate_ids({"1"}, set(), True)
        self.assertEqual(status, "PASS")
        self.assertIn("một chiều", message)

    def test_empty_non_required_endpoint_skips(self):
        status, _ = MODULE.evaluate_ids(set(), set(), False)
        self.assertEqual(status, "SKIP")

    def test_both_users_without_accounts_is_blocked(self):
        status, _ = MODULE.evaluate_ids(set(), set(), True)
        self.assertEqual(status, "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
