"""Read-only two-user isolation audit for Finora.

Only POST is /api/auth/login. All protected data endpoints use GET.
This script never creates, updates, transfers, or deletes financial records.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

import requests

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "10"))


@dataclass
class User:
    label: str
    email: str
    password: str
    token: str = ""


def say(status: str, message: str) -> None:
    print(f"[{status}] {message}")


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
    if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
        say("FAIL", f"GET {path} cho {user.label}: response không phải danh sách object JSON.")
        return None
    return body


def evaluate_ids(ids_a: set[str], ids_b: set[str], required: bool = False) -> tuple[str, str]:
    """Classify disjoint/non-disjoint IDs without making HTTP calls."""
    if not ids_a and not ids_b:
        return ("BLOCKED", "cả hai người dùng đều chưa có tài khoản tài chính để làm dữ liệu đối chiếu") if required else ("SKIP", "cả hai người dùng đều chưa có dữ liệu; chưa có bản ghi để kiểm tra cách ly")
    overlap = ids_a & ids_b
    if overlap:
        examples = ", ".join(sorted(overlap)[:8])
        return "FAIL", f"hai người dùng nhận chung ID ({examples}); cần kiểm tra lọc theo userId"
    if ids_a and ids_b:
        return "PASS", f"{len(ids_a)} ID của A và {len(ids_b)} ID của B, không trùng"
    if ids_a:
        return "PASS", f"A có {len(ids_a)} bản ghi, B có 0; chưa đủ dữ liệu B để kiểm tra hai chiều"
    return "PASS", f"B có {len(ids_b)} bản ghi, A có 0; chưa đủ dữ liệu A để kiểm tra hai chiều"


def compare_resource(
    user_a: User,
    user_b: User,
    label: str,
    endpoint: str,
    id_field: str,
    required: bool = False,
) -> tuple[int, int, int, int]:
    a_rows = get_list(user_a, endpoint)
    b_rows = get_list(user_b, endpoint)
    if a_rows is None or b_rows is None:
        return 0, 1, 0, 0

    missing_a = sum(row.get(id_field) is None for row in a_rows)
    missing_b = sum(row.get(id_field) is None for row in b_rows)
    if missing_a or missing_b:
        say("FAIL", f"{label}: thiếu trường ID '{id_field}' ở A={missing_a}, B={missing_b}.")
        return 0, 1, 0, 0

    ids_a = {str(row[id_field]) for row in a_rows}
    ids_b = {str(row[id_field]) for row in b_rows}
    status, explanation = evaluate_ids(ids_a, ids_b, required)
    say(status, f"Cách ly {label}: {explanation}.")
    if status == "PASS":
        return 1, 0, 0, 0
    if status == "FAIL":
        return 0, 1, 0, 0
    if status == "SKIP":
        return 0, 0, 1, 0
    return 0, 0, 0, 1


def check_stats(user_a: User, user_b: User) -> tuple[int, int, int, int]:
    """Validate per-user stats endpoint responses and report values.

    This is an endpoint/shape sanity check; unlike ID-list comparison it does not
    by itself prove cross-user isolation for aggregated totals.
    """
    today = date.today()
    first_day = today.replace(day=1).isoformat()
    query = urlencode({"tuNgay": first_day, "denNgay": today.isoformat()})
    passed = failed = skipped = blocked = 0

    for user in (user_a, user_b):
        daily = get_list(user, "/api/thong-ke/theo-ngay")
        if daily is None:
            failed += 1
        else:
            say("PASS", f"Thống kê theo ngày {user.label}: response là danh sách JSON ({len(daily)} dòng).")
            passed += 1

        ok, overview = get_json(user, f"/api/thong-ke/tong-quan?{query}")
        required_keys = {"tongThu", "tongChi", "chenhLech", "soGiaoDich"}
        if not ok or not isinstance(overview, dict) or not required_keys.issubset(overview):
            say("FAIL", f"Thống kê tổng quan {user.label}: thiếu object hoặc trường bắt buộc {sorted(required_keys)}.")
            failed += 1
        else:
            say(
                "PASS",
                f"Thống kê tổng quan {user.label} ({first_day} → {today.isoformat()}): "
                f"thu={overview.get('tongThu')}, chi={overview.get('tongChi')}, "
                f"chênh lệch={overview.get('chenhLech')}, số giao dịch={overview.get('soGiaoDich')}.",
            )
            passed += 1
    return passed, failed, skipped, blocked


def main() -> int:
    print(f"Finora user-isolation audit v5 (READ-ONLY): {BASE_URL}")
    print("Sau đăng nhập, các endpoint dữ liệu chỉ được gọi bằng GET; không tạo/sửa/xóa dữ liệu.\n")
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
        say("BLOCKED", "A và B phải là hai tài khoản người dùng khác nhau.")
        return 2

    a = User("A", env["email_a"], env["password_a"])
    b = User("B", env["email_b"], env["password_b"])
    if not login(a) or not login(b):
        say("BLOCKED", "Không tiếp tục audit vì không đăng nhập được cả hai người dùng.")
        return 2

    totals = [0, 0, 0, 0]  # PASS, FAIL, SKIP, BLOCKED
    resources = [
        ("tài khoản", "/api/tai-khoan", "tkId", True),
        ("danh mục", "/api/danh-muc", "danhMucId", False),
        ("lịch sử thu/chi", "/api/giao-dich", "giaoDichId", False),
        ("lịch sử chuyển tiền", "/api/chuyen-khoan", "chuyenKhoanId", False),
        ("ngân sách", "/api/ngan-sach", "nganSachId", False),
    ]
    for label, endpoint, key, required in resources:
        result = compare_resource(a, b, label, endpoint, key, required)
        totals = [x + y for x, y in zip(totals, result)]

    stats = check_stats(a, b)
    totals = [x + y for x, y in zip(totals, stats)]

    print(f"\nKết quả audit: {totals[0]} PASS; {totals[1]} FAIL; {totals[2]} SKIP; {totals[3]} BLOCKED.")
    print("Lưu ý: thống kê tổng quan/theo ngày mới được kiểm tra endpoint và cấu trúc phản hồi; không xem riêng kết quả này là bằng chứng chắc chắn về cách ly số liệu tổng hợp.")
    print("Các endpoint chỉ có dữ liệu ở một người dùng được ghi rõ là kiểm tra một chiều; không tự tạo giao dịch/chuyển tiền/ngân sách để lấp dữ liệu.")
    return 1 if totals[1] else (2 if totals[3] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
