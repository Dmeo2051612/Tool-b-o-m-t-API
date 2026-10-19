#!/usr/bin/env python3
"""Guarded negative authorization tests for cross-user transfers via the Finora API.

Default mode is read-only (aside from POST login). Negative POST checks are opt-in
and require a command-line flag, environment flag, and exact interactive confirmation.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FINORA_API_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
STATE_PATH = Path(__file__).resolve().parent / "finora_cross_user_transfer_state.json"
AMOUNT = "1.00"
CONFIRMATION = "RUN CROSS-USER NEGATIVE TESTS"


def norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def http_json(method: str, path: str, *, token: str | None = None,
              payload: dict[str, Any] | None = None, idempotency_key: str | None = None, timeout: int = 15):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = raw
            return response.status, body
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        return error.code, body
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"Không kết nối được {path}: {error}") from error


def find_value(obj: Any, names: tuple[str, ...]) -> Any:
    wanted = {norm(name) for name in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm(str(key)) in wanted and value is not None:
                return value
        for value in obj.values():
            found = find_value(value, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_value(value, names)
            if found is not None:
                return found
    return None


def to_list(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        # Prefer common API envelopes, then search nested objects for a list.
        for key in ("data", "items", "results", "value", "records"):
            if key in obj:
                result = to_list(obj[key])
                if result or isinstance(obj[key], list):
                    return result
        for value in obj.values():
            if isinstance(value, list):
                result = to_list(value)
                if result or not value:
                    return result
    return []


def field(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    wanted = {norm(name) for name in names}
    for key, value in row.items():
        if norm(str(key)) in wanted:
            return value
    return None


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def login(email: str, password: str, label: str) -> str:
    status, body = http_json("POST", "/api/auth/login", payload={"email": email, "matKhau": password})
    if not 200 <= status < 300:
        raise RuntimeError(f"Đăng nhập {label} thất bại: HTTP {status}; phản hồi={body}")
    token = find_value(body, ("accessToken", "access_token", "token", "jwt"))
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"Đăng nhập {label}: không tìm thấy access token trong phản hồi.")
    print(f"[PASS] Đăng nhập {label} ({email}).")
    return token


def get_list(token: str, path: str, label: str) -> list[dict[str, Any]]:
    status, body = http_json("GET", path, token=token)
    if not 200 <= status < 300:
        raise RuntimeError(f"GET {path} ({label}) thất bại: HTTP {status}; phản hồi={body}")
    return to_list(body)


def parse_accounts(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    found = {}
    for row in rows:
        ident = as_int(field(row, ("tkId", "tk_id", "taiKhoanId", "id")))
        if ident is not None:
            found[ident] = {
                "id": ident,
                "name": str(field(row, ("tenTk", "ten_tk", "tenTaiKhoan", "name")) or ""),
                "balance": as_decimal(field(row, ("soduHienTai", "sodu_hientai", "soDuHienTai", "currentBalance", "balance"))),
                "currency": str(field(row, ("donviTienTe", "donvi_tiente", "currency", "maTienTe")) or "").lower(),
            }
    return found


def transfer_id_set(rows: list[dict[str, Any]]) -> set[str]:
    ids = set()
    for row in rows:
        ident = field(row, ("chuyenKhoanId", "chuyen_khoan_id", "id"))
        if ident is not None:
            ids.add(str(ident))
    return ids


def read_snapshot(token_a: str, token_b: str):
    accounts_a = parse_accounts(get_list(token_a, "/api/tai-khoan", "A accounts"))
    accounts_b = parse_accounts(get_list(token_b, "/api/tai-khoan", "B accounts"))
    transfers_a = transfer_id_set(get_list(token_a, "/api/chuyen-khoan", "A transfers"))
    transfers_b = transfer_id_set(get_list(token_b, "/api/chuyen-khoan", "B transfers"))
    return {
        "accounts_a": accounts_a,
        "accounts_b": accounts_b,
        "transfers_a": transfers_a,
        "transfers_b": transfers_b,
    }


def print_inventory(snapshot):
    print(f"[PASS] Tài khoản A đọc được: {len(snapshot['accounts_a'])}; lịch sử chuyển khoản A: {len(snapshot['transfers_a'])} bản ghi.")
    print(f"[PASS] Tài khoản B đọc được: {len(snapshot['accounts_b'])}; lịch sử chuyển khoản B: {len(snapshot['transfers_b'])} bản ghi.")
    print("\nTài khoản A:")
    for account in snapshot["accounts_a"].values():
        print(f"  ID={account['id']} | {account['name']} | số dư={account['balance']} | tiền tệ={account['currency']}")
    print("\nTài khoản B:")
    for account in snapshot["accounts_b"].values():
        print(f"  ID={account['id']} | {account['name']} | số dư={account['balance']} | tiền tệ={account['currency']}")


def load_or_create_state(owner_a: str, owner_b: str, src_id: int, dest_id: int):
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Không đọc được file state {STATE_PATH}: {error}") from error
        if state.get("emailA", "").lower() != owner_a.lower() or state.get("emailB", "").lower() != owner_b.lower():
            raise RuntimeError("File state đang thuộc cặp email khác; không ghi đè. Hãy kiểm tra file trước khi tiếp tục.")
        if state.get("sourceAccountB") != src_id or state.get("destinationAccountA") != dest_id:
            raise RuntimeError("File state đã lưu ID tài khoản khác; không tự sinh khóa mới để tránh lặp thao tác.")
        return state
    state = {
        "version": 1,
        "emailA": owner_a,
        "emailB": owner_b,
        "sourceAccountB": src_id,
        "destinationAccountA": dest_id,
        "amount": AMOUNT,
        "tests": {
            "A_uses_B_source": {"key": str(uuid.uuid4()), "note": "SECURITY TEST A USING B SOURCE"},
            "B_uses_A_destination": {"key": str(uuid.uuid4()), "note": "SECURITY TEST B USING A DESTINATION"},
        },
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Đã lưu khóa/payload trước khi gửi POST vào {STATE_PATH.name}.")
    return state


def amount_is_valid(account: dict[str, Any]) -> bool:
    return account["balance"] is not None and account["balance"] >= Decimal(AMOUNT)


def run_negative_case(principal_label: str, token: str, payload: dict[str, Any], idempotency_key: str, baseline, token_a: str, token_b: str) -> bool:
    print(f"\nKiểm tra {principal_label}: POST chuyển tiền dùng ID thuộc hai người dùng khác nhau...")
    try:
        status, body = http_json("POST", "/api/chuyen-khoan", token=token, payload=payload, idempotency_key=idempotency_key, timeout=20)
    except RuntimeError as error:
        print(f"[BLOCKED] Không xác định được kết quả POST do lỗi kết nối: {error}")
        print("Không gửi lại tự động. Giữ file state và kiểm tra lịch sử/số dư trước khi chạy lại.")
        return False

    if 200 <= status < 300:
        print(f"[FAIL] API chấp nhận yêu cầu cross-user (HTTP {status}); phản hồi={body}")
        print("DỪNG NGAY: không gửi yêu cầu negative test thứ hai. Kiểm tra DB balances/history trước mọi thao tác khác.")
        return False
    if 400 <= status < 500:
        print(f"[PASS] API từ chối yêu cầu cross-user bằng HTTP {status}.")
    else:
        print(f"[FAIL] API trả HTTP {status}, không phải phản hồi từ chối 4xx mong đợi; phản hồi={body}")
        print("Dừng để xác minh dữ liệu trước khi tiếp tục.")
        return False

    try:
        current = read_snapshot(token_a, token_b)
    except RuntimeError as error:
        print(f"[BLOCKED] Không đọc được dữ liệu sau yêu cầu để xác nhận không thay đổi: {error}")
        return False
    unchanged = True
    for who in ("A", "B"):
        before_acc = baseline[f"accounts_{who.lower()}"]
        after_acc = current[f"accounts_{who.lower()}"]
        for ident, before in before_acc.items():
            after = after_acc.get(ident)
            if after is None or after["balance"] != before["balance"]:
                print(f"[FAIL] Số dư tài khoản {who} #{ident} thay đổi: trước={before['balance']}, sau={None if after is None else after['balance']}.")
                unchanged = False
        before_transfers = baseline[f"transfers_{who.lower()}"]
        after_transfers = current[f"transfers_{who.lower()}"]
        if before_transfers != after_transfers:
            print(f"[FAIL] Lịch sử chuyển khoản {who} thay đổi: trước={sorted(before_transfers)}, sau={sorted(after_transfers)}.")
            unchanged = False
    if unchanged:
        print("[PASS] Số dư tài khoản A/B và lịch sử chuyển khoản không thay đổi sau yêu cầu bị từ chối.")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Negative tests for cross-user transfer authorization. Default mode is GET-only after login.")
    parser.add_argument("--run-negative-write-tests", action="store_true", help="Send guarded POST requests expected to be rejected; inspect README first.")
    args = parser.parse_args()
    print(f"Finora cross-user transfer authorization test: {BASE_URL}")
    print("Mặc định chỉ đăng nhập và GET. Negative POST cần --run-negative-write-tests, FINORA_ALLOW_CROSS_USER_TESTS=YES và xác nhận tương tác.")

    required = {
        "FINORA_EMAIL": os.getenv("FINORA_EMAIL"),
        "FINORA_PASSWORD": os.getenv("FINORA_PASSWORD"),
        "FINORA_SECOND_EMAIL": os.getenv("FINORA_SECOND_EMAIL"),
        "FINORA_SECOND_PASSWORD": os.getenv("FINORA_SECOND_PASSWORD"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        print(f"[BLOCKED] Thiếu biến môi trường: {', '.join(missing)}.")
        return 2

    try:
        token_a = login(required["FINORA_EMAIL"], required["FINORA_PASSWORD"], "người dùng A")
        token_b = login(required["FINORA_SECOND_EMAIL"], required["FINORA_SECOND_PASSWORD"], "người dùng B")
        baseline = read_snapshot(token_a, token_b)
    except RuntimeError as error:
        print(f"[BLOCKED] {error}")
        return 2
    print_inventory(baseline)

    ids_a = set(baseline["accounts_a"])
    ids_b = set(baseline["accounts_b"])
    overlap = ids_a & ids_b
    if overlap:
        print(f"[FAIL] Các ID tài khoản xuất hiện ở cả A và B: {sorted(overlap)}.")
        return 1
    print("[PASS] Không có ID tài khoản dùng chung giữa A và B.")

    if not args.run_negative_write_tests:
        print("\n[INFO] Chế độ chỉ đọc: chưa gửi POST chuyển tiền.")
        print("Để chạy negative authorization test trên tài khoản TEST, đọc README rồi bật FINORA_ALLOW_CROSS_USER_TESTS=YES và dùng --run-negative-write-tests.")
        return 0
    if os.getenv("FINORA_ALLOW_CROSS_USER_TESTS") != "YES":
        print("[BLOCKED] Cần FINORA_ALLOW_CROSS_USER_TESTS=YES.")
        return 2
    if not sys.stdin.isatty():
        print("[BLOCKED] Cần terminal tương tác để xác nhận an toàn.")
        return 2

    print("\nCẢNH BÁO: script sẽ gửi tối đa hai POST chuyển tiền 1.00 VND nhưng dùng một đầu tài khoản không thuộc người dùng đang đăng nhập.")
    print("Mục tiêu là xác minh API từ chối và không thay đổi số dư/lịch sử. Nếu API có lỗ hổng, dữ liệu có thể bị tác động.")
    answer = input(f'Gõ chính xác "{CONFIRMATION}" để tiếp tục: ').strip()
    if answer != CONFIRMATION:
        print("[BLOCKED] Xác nhận không khớp; không gửi POST.")
        return 2

    while True:
        try:
            src_id = int(input("Nhập ID tài khoản TEST nguồn thuộc B: ").strip())
            dest_id = int(input("Nhập ID tài khoản TEST đích thuộc A: ").strip())
        except ValueError:
            print("[BLOCKED] ID phải là số nguyên.")
            return 2
        if src_id not in baseline["accounts_b"] or dest_id not in baseline["accounts_a"]:
            print("[BLOCKED] ID nguồn phải thuộc danh sách B và ID đích phải thuộc danh sách A.")
            return 2
        src = baseline["accounts_b"][src_id]
        dest = baseline["accounts_a"][dest_id]
        if src["balance"] is None or dest["balance"] is None:
            print("[BLOCKED] API không trả về số dư dạng số; không thể xác minh an toàn.")
            return 2
        if src["balance"] < Decimal(AMOUNT):
            print(f"[BLOCKED] Tài khoản nguồn B #{src_id} không đủ số dư {AMOUNT}; hiện có {src['balance']}.")
            return 2
        if src["currency"] and dest["currency"] and src["currency"] != dest["currency"]:
            print(f"[BLOCKED] Tiền tệ khác nhau: nguồn={src['currency']}, đích={dest['currency']}.")
            return 2
        if src_id == dest_id:
            print("[BLOCKED] Nguồn và đích không thể là cùng ID.")
            return 2
        break

    try:
        state = load_or_create_state(required["FINORA_EMAIL"], required["FINORA_SECOND_EMAIL"], src_id, dest_id)
    except RuntimeError as error:
        print(f"[BLOCKED] {error}")
        return 2

    tests = [
        ("A dùng tài khoản nguồn thuộc B", token_a, state["tests"]["A_uses_B_source"], True),
        ("B dùng tài khoản đích thuộc A", token_b, state["tests"]["B_uses_A_destination"], False),
    ]
    passed = 0
    for label, token, spec, a_uses_b_source in tests:
        payload = {
            "tkNguonId": src_id,
            "tkDichId": dest_id,
            "soTien": 1.00,
            "moTa": spec["note"],
        }
        baseline_key = "baseline"
        # A-sourced test is constructed by changing only the auth principal. In both cases
        # the transfer body deliberately crosses ownership boundary (B source -> A destination).
        if not run_negative_case(label, token, payload, spec["key"], baseline, token_a, token_b):
            print("\nDừng kiểm thử vì một yêu cầu chưa được xác minh an toàn. Giữ nguyên file state.")
            return 1
        passed += 1
    print(f"\nKết quả negative cross-user transfer: {passed} PASS; 0 FAIL.")
    print(f"Giữ nguyên file state: {STATE_PATH}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
