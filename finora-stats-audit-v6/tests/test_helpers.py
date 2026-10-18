import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_finora_stats_against_transactions import (  # noqa: E402
    close_money,
    date_text,
    history_totals,
    money,
    stats_totals,
)


class AuditHelpersTests(unittest.TestCase):
    def test_money_normalizes_cents(self):
        self.assertEqual(money(1), Decimal("1.00"))
        self.assertEqual(money("2.015"), Decimal("2.02"))

    def test_iso_date_and_timestamp(self):
        self.assertEqual(date_text("2026-10-05"), date(2026, 10, 5))
        self.assertEqual(date_text("2026-10-05T12:30:00Z"), date(2026, 10, 5))
        self.assertIsNone(date_text("bad-date"))

    def test_history_totals_for_range(self):
        rows = [
            {"giaoDichId": 1, "ngayGd": "2026-10-02", "loaiGd": "thu", "soTien": 10},
            {"giaoDichId": 2, "ngayGd": "2026-10-03T10:00:00Z", "loaiGd": "chi", "soTien": 4.25},
            {"giaoDichId": 3, "ngayGd": "2026-09-30", "loaiGd": "thu", "soTien": 100},
        ]
        result = history_totals(rows, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1], Decimal("10.00"))
        self.assertEqual(result[2], Decimal("4.25"))
        self.assertEqual(result[3][date(2026, 10, 3)], (Decimal("0.00"), Decimal("4.25")))

    def test_daily_totals_for_range(self):
        rows = [
            {"ngay": "2026-10-01", "tongThu": 10, "tongChi": 2},
            {"ngay": "2026-10-02", "tongThu": 5, "tongChi": 1},
            {"ngay": "2026-09-30", "tongThu": 500, "tongChi": 0},
        ]
        income, expense, by_day = stats_totals(rows, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(income, Decimal("15.00"))
        self.assertEqual(expense, Decimal("3.00"))
        self.assertEqual(len(by_day), 2)

    def test_money_tolerance_one_cent(self):
        self.assertTrue(close_money(Decimal("10.00"), Decimal("10.01")))
        self.assertFalse(close_money(Decimal("10.00"), Decimal("10.02")))


if __name__ == "__main__":
    unittest.main()
