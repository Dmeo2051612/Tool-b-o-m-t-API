"""Read-only Finora audit: reconcile per-user overview/daily stats with transactions.

POST is used only for /api/auth/login. Every financial/data endpoint is GET.
No files containing credentials are created and no financial data is modified.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

import requests

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "10"))
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


@dataclass
class User:
    label: str
    email: str
    password: str
    token: str = ""


def say(status: str, message: str) -> None:
    print(f"[{status}] {message}")


def money(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("missing amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid amount {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite amount {value!r}")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def date_text(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        # API dates may be YYYY-MM-DD or ISO timestamps.
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def login(user: User) -> bool:
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": user.email, "matKhau": user.password},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        say("FAIL", f"Đăng nhập {user.label}: không kết nối được ({type(exc).__name__}).")
        return False
    if not response.ok:
        say("FAIL", f"Đăng nhập {user.label}: HTTP {response.status_code}.")
        return False
    try:
        body = response.json()
    except ValueError:
        say("FAIL", f"Đăng nhập {user.label}: response không phải JSON.")
        return False
    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        say("FAIL", f"Đăng nhập {user.label}: thiếu accessToken.")
        return False
    user.token = token
    say("PASS", f"Đăng nhập người dùng {user.label} ({user.email}).")
    return True


def get_json(user: User, path: str) -> tuple[bool, Any]:
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {user.token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        say("FAIL", f"GET {path} cho {user.label}: không kết nối được ({type(exc).__name__}).")
        return False, None
    if not response.ok:
        say("FAIL", f"GET {path} cho {user.label}: HTTP {response.status_code}.")
        return False, None
    try:
        return True, response.json()
    except ValueError:
        say("FAIL", f"GET {path} cho {user.label}: response không phải JSON.")
        return False, None


def get_list(user: User, path: str) -> list[dict[str, Any]] | None:
    ok, body = get_json(user, path)
    if not ok:
        return None
    if not isinstance(body, list) or any(not isinstance(row, dict) for row in body):
        say("FAIL", f"GET {path} cho {user.label}: không trả về danh sách object JSON.")
        return None
    return body


def as_count(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean count")
    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise ValueError("non-integer count")
    count = int(number)
    if count < 0:
        raise ValueError("negative count")
    return count


def close_money(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= CENT


def stats_totals(daily_rows: list[dict[str, Any]], start: date, end: date) -> tuple[Decimal, Decimal, dict[date, tuple[Decimal, Decimal]]]:
    income = ZERO
    expense = ZERO
    by_day: dict[date, tuple[Decimal, Decimal]] = {}
    for row in daily_rows:
        day = date_text(row.get("ngay"))
        if day is None:
            raise ValueError("daily stats row missing/invalid 'ngay'")
        try:
            row_income = money(row.get("tongThu", 0))
            row_expense = money(row.get("tongChi", 0))
        except ValueError as exc:
            raise ValueError(f"invalid daily totals on {day.isoformat()}: {exc}") from exc
        if day < start or day > end:
            continue
        income += row_income
        expense += row_expense
        old_income, old_expense = by_day.get(day, (ZERO, ZERO))
        by_day[day] = (old_income + row_income, old_expense + row_expense)
    return income.quantize(CENT), expense.quantize(CENT), by_day


def history_totals(
    rows: list[dict[str, Any]], start: date, end: date
) -> tuple[int, Decimal, Decimal, dict[date, tuple[Decimal, Decimal]], int]:
    count = 0
    income = ZERO
    expense = ZERO
    by_day: dict[date, tuple[Decimal, Decimal]] = {}
    skipped_dates = 0
    for row in rows:
        day = date_text(row.get("ngayGd"))
        if day is None:
            skipped_dates += 1
            continue
        if day < start or day > end:
            continue
        try:
            amount = money(row.get("soTien"))
        except ValueError as exc:
            raise ValueError(f"giaoDichId={row.get('giaoDichId')}: thiếu/sai soTien") from exc
        kind = str(row.get("loaiGd", "")).strip().casefold()
        if kind not in {"thu", "chi"}:
            raise ValueError(f"giaoDichId={row.get('giaoDichId')}: loaiGd không phải thu/chi")
        count += 1
        day_income, day_expense = by_day.get(day, (ZERO, ZERO))
        if kind == "thu":
            income += amount
            day_income += amount
        else:
            expense += amount
            day_expense += amount
        by_day[day] = (day_income.quantize(CENT), day_expense.quantize(CENT))
    return count, income.quantize(CENT), expense.quantize(CENT), by_day, skipped_dates


def audit_user(user: User, start: date, end: date) -> tuple[int, int, int]:
    """Return (pass, fail, blocked)."""
    passed = failed = blocked = 0
    query = urlencode({"tuNgay": start.isoformat(), "denNgay": end.isoformat()})

    transactions = get_list(user, "/api/giao-dich")
    daily_rows = get_list(user, f"/api/thong-ke/theo-ngay?{query}")
    ok_summary, summary = get_json(user, f"/api/thong-ke/tong-quan?{query}")

    if transactions is None:
        failed += 1
    if daily_rows is None:
        failed += 1
    if not ok_summary or not isinstance(summary, dict):
        failed += 1
    if transactions is None or daily_rows is None or not ok_summary or not isinstance(summary, dict):
        return passed, failed, blocked

    required = {"tongThu", "tongChi", "chenhLech", "soGiaoDich"}
    if not required.issubset(summary):
        say("FAIL", f"Audit {user.label}: tổng quan thiếu trường {sorted(required - set(summary))}.")
        return passed, failed + 1, blocked

    try:
        summary_income = money(summary["tongThu"])
        summary_expense = money(summary["tongChi"])
        summary_net = money(summary["chenhLech"])
        summary_count = as_count(summary["soGiaoDich"])
        daily_income, daily_expense, daily_by_day = stats_totals(daily_rows, start, end)
        hist_count, hist_income, hist_expense, hist_by_day, skipped_dates = history_totals(transactions, start, end)
    except ValueError as exc:
        say("FAIL", f"Audit {user.label}: dữ liệu JSON không hợp lệ ({exc}).")
        return passed, failed + 1, blocked

    if close_money(summary_net, summary_income - summary_expense):
        say("PASS", f"Thống kê tổng quan {user.label}: chênh lệch khớp thu - chi ({summary_net}).")
        passed += 1
    else:
        say("FAIL", f"Thống kê tổng quan {user.label}: chênh lệch={summary_net}, nhưng thu-chi={summary_income-summary_expense}.")
        failed += 1

    if close_money(daily_income, summary_income) and close_money(daily_expense, summary_expense):
        say("PASS", f"Thống kê theo ngày ↔ tổng quan {user.label}: thu={daily_income}, chi={daily_expense} khớp.")
        passed += 1
    else:
        say("FAIL", f"Thống kê theo ngày ↔ tổng quan {user.label}: ngày thu={daily_income}/tổng quan={summary_income}; ngày chi={daily_expense}/tổng quan={summary_expense}.")
        failed += 1

    if hist_count != summary_count:
        say(
            "BLOCKED",
            f"Lịch sử ↔ tổng quan {user.label}: lịch sử có {hist_count} giao dịch trong khoảng, tổng quan báo {summary_count}; "
            "không kết luận lệch số liệu vì GET /api/giao-dich có thể giới hạn/paginate."
        )
        blocked += 1
    elif skipped_dates:
        say("BLOCKED", f"Lịch sử ↔ tổng quan {user.label}: {skipped_dates} dòng lịch sử không có ngày hợp lệ; chưa đối chiếu đủ.")
        blocked += 1
    elif close_money(hist_income, summary_income) and close_money(hist_expense, summary_expense):
        say("PASS", f"Lịch sử ↔ tổng quan {user.label}: {hist_count} giao dịch, thu={hist_income}, chi={hist_expense} khớp.")
        passed += 1
    else:
        say("FAIL", f"Lịch sử ↔ tổng quan {user.label}: lịch sử thu={hist_income}, chi={hist_expense}; tổng quan thu={summary_income}, chi={summary_expense}.")
        failed += 1

    if hist_count == summary_count and not skipped_dates:
        all_days = sorted(set(hist_by_day) | set(daily_by_day))
        mismatched = []
        for day in all_days:
            h_income, h_expense = hist_by_day.get(day, (ZERO, ZERO))
            d_income, d_expense = daily_by_day.get(day, (ZERO, ZERO))
            if not close_money(h_income, d_income) or not close_money(h_expense, d_expense):
                mismatched.append((day.isoformat(), h_income, d_income, h_expense, d_expense))
        if not mismatched:
            say("PASS", f"Lịch sử ↔ theo ngày {user.label}: các ngày có dữ liệu khớp ({len(all_days)} ngày được so sánh).")
            passed += 1
        else:
            detail = "; ".join(f"{d}: thu {hi}/{di}, chi {he}/{de}" for d, hi, di, he, de in mismatched[:3])
            say("FAIL", f"Lịch sử ↔ theo ngày {user.label}: lệch {len(mismatched)} ngày. Ví dụ: {detail}.")
            failed += 1
    else:
        say("BLOCKED", f"Lịch sử ↔ theo ngày {user.label}: bỏ qua so sánh theo từng ngày vì chưa chứng minh lịch sử đầy đủ.")
        blocked += 1
    return passed, failed, blocked


def main() -> int:
    print(f"Finora stats reconciliation v6 (READ-ONLY): {BASE_URL}")
    print("Sau đăng nhập, dữ liệu tài chính chỉ được gọi bằng GET; không tạo/sửa/xóa dữ liệu.\n")
    env = {
        "email_a": os.getenv("FINORA_EMAIL", "").strip(),
        "password_a": os.getenv("FINORA_PASSWORD", ""),
        "email_b": os.getenv("FINORA_SECOND_EMAIL", "").strip(),
        "password_b": os.getenv("FINORA_SECOND_PASSWORD", ""),
    }
    if not all(env.values()):
        say("BLOCKED", "Cần đặt FINORA_EMAIL, FINORA_PASSWORD, FINORA_SECOND_EMAIL và FINORA_SECOND_PASSWORD trong PowerShell.")
        return 2
    if env["email_a"].casefold() == env["email_b"].casefold():
        say("BLOCKED", "A và B phải là hai người dùng khác nhau.")
        return 2

    end = date.today()
    start = end.replace(day=1)
    print(f"Khoảng đối chiếu: {start.isoformat()} → {end.isoformat()}\n")
    users = [User("A", env["email_a"], env["password_a"]), User("B", env["email_b"], env["password_b"])]
    if not login(users[0]) or not login(users[1]):
        say("BLOCKED", "Không tiếp tục vì không đăng nhập được cả hai người dùng.")
        return 2

    totals = [0, 0, 0]  # PASS, FAIL, BLOCKED
    for user in users:
        print(f"\n--- Đối chiếu thống kê cho người dùng {user.label} ({user.email}) ---")
        counts = audit_user(user, start, end)
        totals = [x + y for x, y in zip(totals, counts)]

    print(f"\nKết quả audit thống kê: {totals[0]} PASS; {totals[1]} FAIL; {totals[2]} BLOCKED.")
    print("BLOCKED không tự động có nghĩa là lỗi: nếu lịch sử API bị giới hạn, cần xác minh phân trang/giới hạn trước khi kết luận.")
    print("Script chỉ thực hiện POST đăng nhập; các endpoint tài chính được gọi bằng GET.")
    return 1 if totals[1] else (2 if totals[2] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
