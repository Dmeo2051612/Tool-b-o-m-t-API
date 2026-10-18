"""Read-only integration test for per-user API data isolation.

Logs in as two test users and makes only GET requests after authentication.
It never creates, edits, transfers, or deletes financial data.
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
        say("FAIL", f"Đăng nhập người dùng {user.label}: không kết nối được ({type(exc).__name__})")
        return False

    if not response.ok:
        say("FAIL", f"Đăng nhập người dùng {user.label}: HTTP {response.status_code}")
        return False

    try:
        body = response.json()
    except ValueError:
        say("FAIL", f"Đăng nhập người dùng {user.label}: phản hồi không phải JSON")
        return False

    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        say("FAIL", f"Đăng nhập người dùng {user.label}: không có accessToken")
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
    if any(not isinstance(item, dict) for item in body):
        say("FAIL", f"{user.label} {endpoint}: danh sách có phần tử không phải object")
        return None

    return body


def evaluate_ids(ids_a: set[str], ids_b: set[str], require_data: bool) -> tuple[str, str]:
    """Return status + explanation for one endpoint without making HTTP calls."""
    if not ids_a and not ids_b:
        if require_data:
            return "BLOCKED", "cả hai người dùng đều chưa có tài khoản tài chính để làm dữ liệu đối chiếu"
        return "SKIP", "cả hai người dùng đều chưa có dữ liệu; chưa có bản ghi để kiểm tra cách ly"

    overlap = ids_a & ids_b
    if overlap:
        examples = ", ".join(sorted(overlap)[:5])
        return "FAIL", f"hai người dùng nhận chung ID ({examples}); cần kiểm tra lọc theo userId"

    if ids_a and ids_b:
        return "PASS", f"{len(ids_a)} ID của A và {len(ids_b)} ID của B, không trùng"

    if ids_a:
        return "PASS", (
            f"A có {len(ids_a)} bản ghi, B có 0; không thấy bản ghi của A trong kết quả B. "
            "Kiểm tra một chiều; chưa thể kiểm tra dữ liệu B sang A khi B chưa có bản ghi"
        )
    return "PASS", (
        f"B có {len(ids_b)} bản ghi, A có 0; không thấy bản ghi của B trong kết quả A. "
        "Kiểm tra một chiều; chưa thể kiểm tra dữ liệu A sang B khi A chưa có bản ghi"
    )


def check_isolation(user_a: TestUser, user_b: TestUser) -> tuple[int, int, int, int]:
    resources = [
        ("tài khoản", "/api/tai-khoan", "tkId", True),
        ("danh mục", "/api/danh-muc", "danhMucId", False),
        ("lịch sử thu/chi", "/api/giao-dich", "giaoDichId", False),
        ("lịch sử chuyển tiền", "/api/chuyen-khoan", "chuyenKhoanId", False),
        ("ngân sách", "/api/ngan-sach", "nganSachId", False),
    ]
    passed = failed = skipped = blocked = 0

    for label, endpoint, key, required in resources:
        data_a = get_list(user_a, endpoint)
        data_b = get_list(user_b, endpoint)
        if data_a is None or data_b is None:
            failed += 1
            continue

        malformed_a = sum(1 for row in data_a if row.get(key) is None)
        malformed_b = sum(1 for row in data_b if row.get(key) is None)
        if malformed_a or malformed_b:
            say(
                "FAIL",
                f"Cô lập {label}: {malformed_a} bản ghi của A và {malformed_b} bản ghi của B thiếu trường ID '{key}'",
            )
            failed += 1
            continue

        ids_a = {str(row[key]) for row in data_a}
        ids_b = {str(row[key]) for row in data_b}
        result, explanation = evaluate_ids(ids_a, ids_b, required)
        say(result, f"Cô lập {label}: {explanation}")
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
        elif result == "SKIP":
            skipped += 1
        elif result == "BLOCKED":
            blocked += 1

    return passed, failed, skipped, blocked


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

    passed, failed, skipped, blocked = check_isolation(user_a, user_b)
    print(f"\nKết quả: {passed} PASS; {failed} FAIL; {skipped} SKIP; {blocked} BLOCKED")
    if skipped:
        print("SKIP nghĩa là cả hai người dùng đều chưa có dữ liệu ở endpoint đó.")
    if blocked:
        print("BLOCKED nghĩa là cả hai người dùng đều chưa có tài khoản tài chính để làm dữ liệu đối chiếu.")
    if passed and any((skipped, blocked)):
        print("Lưu ý: PASS một chiều chỉ kiểm tra rằng bản ghi đang có không xuất hiện trong kết quả người dùng còn lại; muốn kiểm thử hai chiều đầy đủ, hãy tạo dữ liệu riêng cho cả hai người dùng.")
    return 1 if failed else (2 if blocked else 0)


if __name__ == "__main__":
    sys.exit(main())
