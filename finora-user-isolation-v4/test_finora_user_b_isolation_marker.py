"""Finora bidirectional transaction-isolation marker test.

Default mode is read-only (login + GET). A tiny income record for test user B is
created only when --create-marker, FINORA_ALLOW_ISOLATION_WRITE=YES, and an exact
interactive confirmation are all present. The record is never deleted; a saved
Idempotency-Key/payload makes reruns safe.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "10"))
STATE_PATH = Path(__file__).with_name("finora_user_b_isolation_state.json")
MARKER_CONFIRMATION = "CREATE ONE 1 VND TEST INCOME FOR B"


def say(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def api_request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            raw, status = response.read(), response.status
    except HTTPError as exc:
        raw, status = exc.read(), exc.code
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{method} {path}: không kết nối được ({type(exc).__name__})") from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed: Any = json.loads(text) if text else None
    except json.JSONDecodeError:
        parsed = text
    return status, parsed


def login(label: str, email_env: str, password_env: str) -> tuple[str, str]:
    email = os.getenv(email_env, "").strip()
    password = os.getenv(password_env, "")
    if not email or not password:
        raise RuntimeError(f"Cần đặt {email_env} và {password_env} trong PowerShell.")
    status, body = api_request("POST", "/api/auth/login", body={"email": email, "matKhau": password})
    if not 200 <= status < 300:
        raise RuntimeError(f"Đăng nhập người dùng {label} thất bại: HTTP {status}")
    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Đăng nhập người dùng {label}: response thiếu accessToken.")
    say("PASS", f"Đăng nhập người dùng {label} ({email})")
    return email, token


def get_list(token: str, path: str, label: str) -> list[dict[str, Any]]:
    status, body = api_request("GET", path, token=token)
    if not 200 <= status < 300:
        raise RuntimeError(f"{label} GET {path} thất bại: HTTP {status}")
    if not isinstance(body, list) or any(not isinstance(row, dict) for row in body):
        raise RuntimeError(f"{label} GET {path}: response không phải danh sách object JSON.")
    return body


def load_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không đọc được {STATE_PATH.name}; không tự tạo key khác.") from exc
    required = ("ownerEmail", "key", "payload")
    if not isinstance(state, dict) or not all(k in state for k in required):
        raise RuntimeError(f"{STATE_PATH.name} sai định dạng; dừng an toàn.")
    if not isinstance(state["payload"], dict) or not state["key"]:
        raise RuntimeError(f"{STATE_PATH.name} thiếu key/payload; dừng an toàn.")
    return state


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def show_b_options(accounts: list[dict[str, Any]], categories: list[dict[str, Any]]) -> None:
    print("\nTài khoản hiện có của người dùng B:")
    if not accounts:
        print("  (không có tài khoản nào trả về từ API)")
    for row in accounts:
        print(f"  ID={row.get('tkId')} | {row.get('tenTk', 'Tài khoản')} | số dư={row.get('soDuHienTai')} | tiền tệ={row.get('donViTienTe', 'VND')}")
    income_categories = [r for r in categories if str(r.get("loaiGd", "")).strip().casefold() == "thu"]
    print("\nDanh mục thu nhập hiện có của B:")
    if not income_categories:
        print("  (không có danh mục thu nhập nào trả về từ API)")
    for row in income_categories:
        print(f"  ID={row.get('danhMucId')} | {row.get('tenDanhMuc', 'Danh mục thu')}")


def choose_id(prompt: str, allowed: set[str]) -> str:
    value = input(prompt).strip()
    if value not in allowed:
        raise RuntimeError(f"ID '{value}' không nằm trong danh sách B vừa lấy từ API; không gửi POST.")
    return value


def audit_marker(email_a: str, token_a: str, token_b: str, state: dict[str, Any]) -> tuple[int, int, int]:
    marker = str(state["payload"].get("moTa", ""))
    if not marker:
        raise RuntimeError("Payload state không có moTa marker.")
    a_rows = get_list(token_a, "/api/giao-dich", "A")
    b_rows = get_list(token_b, "/api/giao-dich", "B")
    found_a = [r for r in a_rows if str(r.get("moTa", "")) == marker]
    found_b = [r for r in b_rows if str(r.get("moTa", "")) == marker]
    if len(found_b) == 1 and len(found_a) == 0:
        found_id = found_b[0].get("giaoDichId")
        state["markerId"] = found_id
        save_state(state)
        say("PASS", f"Marker của B xuất hiện đúng 1 lần trong lịch sử B và 0 lần ở A (giaoDichId=#{found_id}).")
        return 1, 0, 0
    if len(found_a) > 0:
        say("FAIL", f"Marker của B xuất hiện trong lịch sử A ({len(found_a)} bản ghi); có dấu hiệu lộ dữ liệu.")
        return 0, 1, 0
    if len(found_b) > 1:
        say("FAIL", f"Marker xuất hiện {len(found_b)} lần ở B; kiểm tra database vì có thể đã ghi trùng.")
        return 0, 1, 0
    say("BLOCKED", "Không tìm thấy marker trong lịch sử B. API có thể giới hạn lịch sử; kiểm tra GET response hoặc database trước khi kết luận.")
    return 0, 0, 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Finora B→A transaction isolation check; read-only by default.")
    parser.add_argument("--create-marker", action="store_true", help="tạo đúng một khoản thu TEST 1 VND thuộc người dùng B")
    args = parser.parse_args()

    print(f"Finora B→A isolation marker test: {BASE_URL}")
    print("Mặc định chỉ đăng nhập và GET. Không có thao tác ghi nếu thiếu cả 3 điều kiện: --create-marker, FINORA_ALLOW_ISOLATION_WRITE=YES và xác nhận tương tác.")

    try:
        email_a, token_a = login("A", "FINORA_EMAIL", "FINORA_PASSWORD")
        email_b, token_b = login("B", "FINORA_SECOND_EMAIL", "FINORA_SECOND_PASSWORD")
        if email_a.casefold() == email_b.casefold():
            raise RuntimeError("A và B phải là hai tài khoản người dùng khác nhau.")

        accounts_b = get_list(token_b, "/api/tai-khoan", "B")
        categories_b = get_list(token_b, "/api/danh-muc", "B")
        say("PASS", f"Đọc dữ liệu B: {len(accounts_b)} tài khoản; {len(categories_b)} danh mục.")
        show_b_options(accounts_b, categories_b)
        state = load_state()

        if args.create_marker:
            if os.getenv("FINORA_ALLOW_ISOLATION_WRITE") != "YES":
                raise RuntimeError("Bị chặn: cần đặt $env:FINORA_ALLOW_ISOLATION_WRITE = 'YES'.")
            if not accounts_b:
                say("BLOCKED", "B chưa có tài khoản tài chính. Không thể tạo khoản thu cho B; cần tạo một tài khoản TEST thuộc B trước.")
                return 2
            income_categories = [r for r in categories_b if str(r.get("loaiGd", "")).strip().casefold() == "thu" and r.get("danhMucId") is not None]
            if not income_categories:
                say("BLOCKED", "B chưa có danh mục thu nhập. Không gửi POST.")
                return 2
            if state is not None:
                if str(state.get("ownerEmail", "")).casefold() != email_b.casefold():
                    raise RuntimeError("File state thuộc tài khoản B khác; không dùng lại để tránh ghi nhầm.")
                account_ids = {str(r.get("tkId")) for r in accounts_b}
                category_ids = {str(r.get("danhMucId")) for r in categories_b}
                payload = state["payload"]
                if str(payload.get("tkId")) not in account_ids or str(payload.get("danhMucId")) not in category_ids:
                    raise RuntimeError("Account/category trong state không còn thuộc danh sách B; dừng an toàn.")
                say("INFO", f"Dùng lại key/payload có sẵn trong {STATE_PATH.name}; không tạo key mới.")
            else:
                print("\nCẢNH BÁO: thao tác này sẽ ghi một khoản THU 1.00 VND vào tài khoản TEST của B. Không tự xóa bản ghi.")
                print("File state sẽ giữ Idempotency-Key để chạy lại không tạo marker mới.")
                if input(f'Gõ chính xác "{MARKER_CONFIRMATION}" để tiếp tục: ').strip() != MARKER_CONFIRMATION:
                    say("BLOCKED", "Không có xác nhận chính xác; chưa gửi POST.")
                    return 2
                account_by_id = {str(r.get("tkId")): r for r in accounts_b if r.get("tkId") is not None}
                category_by_id = {str(r.get("danhMucId")): r for r in income_categories}
                account_id = choose_id("Nhập ID tài khoản TEST thuộc B: ", set(account_by_id))
                category_id = choose_id("Nhập ID danh mục thu nhập TEST của B: ", set(category_by_id))
                payload = {
                    "tkId": int(account_id),
                    "danhMucId": int(category_id),
                    "loaiGd": "thu",
                    "soTien": 1.00,
                    "ngayGd": datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "moTa": f"Finora isolation marker B {uuid.uuid4().hex[:12]}",
                }
                state = {
                    "ownerEmail": email_b,
                    "createdAt": datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "key": str(uuid.uuid4()),
                    "payload": payload,
                }
                save_state(state)
                say("INFO", f"Đã lưu key/payload trước khi POST vào {STATE_PATH.name}.")

            status, body = api_request("POST", "/api/giao-dich", token=token_b, body=state["payload"], idempotency_key=str(state["key"]))
            if not 200 <= status < 300:
                say("FAIL", f"Tạo marker trả HTTP {status}; giữ nguyên file state để điều tra/retry cùng key.")
                print(f"Response: {body}")
                return 1
            if isinstance(body, dict) and body.get("giaoDichId") is not None:
                state["markerId"] = body["giaoDichId"]
                save_state(state)
                say("PASS", f"API chấp nhận marker, giaoDichId=#{state['markerId']}.")
            else:
                say("INFO", "POST trả thành công nhưng response không có giaoDichId; sẽ xác minh bằng moTa trong lịch sử.")

        if state is None:
            print("\n[INFO] Chưa có marker state. Chưa gửi POST và chưa kiểm tra chiều B → A cho lịch sử thu/chi.")
            print("Nếu B đã có tài khoản TEST, hãy chạy lại với --create-marker sau khi bật FINORA_ALLOW_ISOLATION_WRITE=YES.")
            return 0

        if str(state.get("ownerEmail", "")).casefold() != email_b.casefold():
            raise RuntimeError("File state không thuộc người dùng B đang đăng nhập; dừng an toàn.")
        passed, failed, blocked = audit_marker(email_a, token_a, token_b, state)
        print(f"\nKết quả kiểm tra marker B→A: {passed} PASS; {failed} FAIL; {blocked} BLOCKED")
        return 1 if failed else (2 if blocked else 0)

    except (RuntimeError, ValueError) as exc:
        say("BLOCKED", str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
