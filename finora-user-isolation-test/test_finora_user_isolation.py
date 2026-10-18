"""Read-only integration test for per-user API data isolation.

Requires two test users. Makes only GET requests after logging in; it does not
create, edit, transfer, or delete financial data.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import requests

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "8"))


@dataclass
class TestUser:
    label: str
    email: str
    password: str
    token: str = ""


def say(status: str, message: str) -> None:
    print(f"[{status}] {message}")


def login(user: TestUser) -> bool:
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": user.email, "matKhau": user.password},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        say("FAIL", f"Đăng nhập {user.label}: không kết nối được ({type(exc).__name__})")
        return False

    if not response.ok:
        say("FAIL", f"Đăng nhập {user.label}: HTTP {response.status_code}")
        return False

    try:
        body = response.json()
    except ValueError:
        say("FAIL", f"Đăng nhập {user.label}: phản hồi không phải JSON")
        return False

    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        say("FAIL", f"Đăng nhập {user.label}: không có accessToken")
        return False

    user.token = token
    say("PASS", f"Đăng nhập người dùng {user.label}")
    return True


def get_list(user: TestUser, endpoint: str) -> list[dict[str, Any]] | None:
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {user.token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        say("FAIL", f"{user.label} {endpoint}: không kết nối được ({type(exc).__name__})")
        return None

    if not response.ok:
        say("FAIL", f"{user.label} {endpoint}: HTTP {response.status_code}")
        return None

    try:
        body = response.json()
    except ValueError:
        say("FAIL", f"{user.label} {endpoint}: phản hồi không phải JSON")
        return None

    if not isinstance(body, list):
        say("FAIL", f"{user.label} {endpoint}: phản hồi không phải danh sách")
        return None

    return [item for item in body if isinstance(item, dict)]


def check_isolation(user_a: TestUser, user_b: TestUser) -> tuple[int, int, int]:
    # ID keys are global primary keys; if either user's list leaks another
    # user's records, the two users' result sets should overlap.
    resources = [
        ("tài khoản", "/api/tai-khoan", "tkId", True),
        ("danh mục", "/api/danh-muc", "danhMucId", False),
        ("lịch sử thu/chi", "/api/giao-dich", "giaoDichId", False),
        ("lịch sử chuyển tiền", "/api/chuyen-khoan", "chuyenKhoanId", False),
        ("ngân sách", "/api/ngan-sach", "nganSachId", False),
    ]
    passed = failed = skipped = 0

    for label, endpoint, key, required in resources:
        data_a = get_list(user_a, endpoint)
        data_b = get_list(user_b, endpoint)
        if data_a is None or data_b is None:
            failed += 1
            continue

        ids_a = {str(row[key]) for row in data_a if row.get(key) is not None}
        ids_b = {str(row[key]) for row in data_b if row.get(key) is not None}

        if required and (not ids_a or not ids_b):
            say("FAIL", f"Cô lập {label}: mỗi tài khoản test cần ít nhất một bản ghi")
            failed += 1
            continue

        if not ids_a or not ids_b:
            say("SKIP", f"Cô lập {label}: một người dùng chưa có dữ liệu để đối chiếu")
            skipped += 1
            continue

        overlap = ids_a & ids_b
        if overlap:
            examples = ", ".join(sorted(overlap)[:5])
            say("FAIL", f"Cô lập {label}: hai người dùng nhận chung ID ({examples}); cần kiểm tra lọc theo userId")
            failed += 1
        else:
            say("PASS", f"Cô lập {label}: {len(ids_a)} ID của {user_a.label}, {len(ids_b)} ID của {user_b.label}, không trùng")
            passed += 1

    return passed, failed, skipped


def main() -> int:
    print(f"Finora user-isolation tests: {BASE_URL}")
    print("Chỉ đăng nhập và GET dữ liệu; không tạo hoặc sửa dữ liệu tài chính.\n")

    email_a = os.getenv("FINORA_EMAIL", "").strip()
    password_a = os.getenv("FINORA_PASSWORD", "")
    email_b = os.getenv("FINORA_SECOND_EMAIL", "").strip()
    password_b = os.getenv("FINORA_SECOND_PASSWORD", "")

    if not all((email_a, password_a, email_b, password_b)):
        print("Cần cấu hình FINORA_EMAIL, FINORA_PASSWORD, FINORA_SECOND_EMAIL và FINORA_SECOND_PASSWORD.")
        print("Dùng hai tài khoản test khác nhau; không đặt mật khẩu trực tiếp trong file script.")
        return 2
    if email_a.casefold() == email_b.casefold():
        print("Hai email test phải thuộc hai người dùng khác nhau.")
        return 2

    user_a = TestUser("A", email_a, password_a)
    user_b = TestUser("B", email_b, password_b)
    if not login(user_a) or not login(user_b):
        print("\nKhông thể tiếp tục vì một trong hai người dùng chưa đăng nhập được.")
        return 1

    passed, failed, skipped = check_isolation(user_a, user_b)
    print(f"\nKết quả: {passed} PASS; {failed} FAIL; {skipped} SKIP")
    if skipped:
        print("SKIP nghĩa là endpoint đó chưa có dữ liệu ở cả hai phía nên chưa đủ căn cứ kiểm tra cách ly.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
