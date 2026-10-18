import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "test_finora_user_isolation.py"
spec = importlib.util.spec_from_file_location("finora_user_isolation", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestIsolationPolicy(unittest.TestCase):
    def test_resource_disjoint_both_users_have_data(self):
        self.assertEqual(
            module.evaluate_ids({"1", "2"}, {"3"}, False),
            ("PASS", "2 ID của A và 1 ID của B, không trùng"),
        )

    def test_resource_overlap_fails(self):
        status, detail = module.evaluate_ids({"4"}, {"4", "5"}, False)
        self.assertEqual(status, "FAIL")
        self.assertIn("chung ID", detail)

    def test_empty_resource_skips(self):
        self.assertEqual(
            module.evaluate_ids(set(), set(), False),
            ("SKIP", "cả hai người dùng đều chưa có dữ liệu; chưa có bản ghi để kiểm tra cách ly"),
        )

    def test_empty_accounts_block(self):
        self.assertEqual(module.evaluate_ids(set(), set(), True)[0], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
