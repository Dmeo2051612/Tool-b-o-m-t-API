"""Read-only audit for Finora idempotency test records; never sends POST."""
from __future__ import annotations
import argparse
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "10"))
STATE_PATH = Path(__file__).with_name("finora_idempotency_test_state.json")


def request_json(method: str, path: str, token: str | None = None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            status, raw = resp.status, resp.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Không kết nối được {method} {path}: {type(exc).__name__}") from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text) if text else None
    except json.JSONDecodeError:
        parsed = text
    return status, parsed


def login(email: str, password: str) -> str:
    status, body = request_json("POST", "/api/auth/login", body={"email": email, "matKhau": password})
    if not 200 <= status < 300:
        raise RuntimeError(f"Đăng nhập thất bại: HTTP {status}")
    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login response thiếu accessToken.")
    print(f"[PASS] Đăng nhập {email}")
    return token


def get_list(token: str, path: str) -> list[dict[str, Any]]:
    status, body = request_json("GET", path, token)
    if not 200 <= status < 300:
        raise RuntimeError(f"GET {path} thất bại: HTTP {status}")
    if not isinstance(body, list) or any(not isinstance(x, dict) for x in body):
        raise RuntimeError(f"GET {path} không trả về danh sách JSON object.")
    return body


def money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def check_test_row(label: str, rows: list[dict[str, Any]], payload: dict[str, Any], id_field: str, amount_field: str = "soTien", compare_fields: tuple[str, ...] = ()) -> bool:
    note = payload.get("moTa")
    matches = [row for row in rows if row.get("moTa") == note]
    if len(matches) != 1:
        print(f"[FAIL] {label}: tìm thấy {len(matches)} bản ghi có mô tả test; mong đợi đúng 1.")
        if not matches:
            print("       Có thể lịch sử API bị giới hạn hoặc bản ghi chưa xuất hiện; kiểm tra trực tiếp database/API.")
        return False
    row = matches[0]
    mismatches = []
    for field in compare_fields:
        expected = payload.get(field)
        actual = row.get(field)
        if field == amount_field:
            if money(actual) != money(expected):
                mismatches.append(f"{field}: API={actual}, payload={expected}")
        elif field == "loaiGd":
            if str(actual).lower() != str(expected).lower():
                mismatches.append(f"{field}: API={actual}, payload={expected}")
        elif actual is None or str(actual) != str(expected):
            mismatches.append(f"{field}: API={actual}, payload={expected}")
    if mismatches:
        print(f"[FAIL] {label}: bản ghi #{row.get(id_field)} có thông tin khác với payload:")
        for mismatch in mismatches:
            print(f"       {mismatch}")
        return False
    print(f"[PASS] {label}: đúng 1 bản ghi, ID=#{row.get(id_field)}, số tiền={row.get(amount_field)}.")
    return True


def parse_balance_spec(value: str) -> tuple[str, Decimal]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Dùng định dạng ID=SODU, ví dụ 4=56000.00")
    account_id, raw_amount = value.split("=", 1)
    if not account_id.strip():
        raise argparse.ArgumentTypeError("Thiếu ID tài khoản.")
    amount = money(raw_amount.strip())
    if amount is None:
        raise argparse.ArgumentTypeError("Số dư không hợp lệ.")
    return account_id.strip(), amount


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dữ liệu đã tạo bởi test idempotency; chỉ GET, không gửi POST.")
    parser.add_argument("--check-balance", action="append", type=parse_balance_spec, default=[], metavar="ID=SODU",
                        help="Kiểm tra số dư hiện tại theo kỳ vọng. Có thể lặp lại, ví dụ --check-balance 4=56000 --check-balance 5=51001")
    args = parser.parse_args()

    print(f"Finora idempotency audit (READ-ONLY): {BASE_URL}")
    print("Script chỉ đăng nhập và GET dữ liệu; không gọi POST ngoài endpoint đăng nhập.")
    email = os.getenv("FINORA_EMAIL", "").strip()
    password = os.getenv("FINORA_PASSWORD", "")
    if not email or not password:
        print("[BLOCKED] Cần đặt FINORA_EMAIL và FINORA_PASSWORD trong PowerShell.")
        return 2
    if not STATE_PATH.exists():
        print(f"[BLOCKED] Không tìm thấy {STATE_PATH.name}. Sao chép file state từ thư mục test idempotency vào thư mục này.")
        return 2
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[BLOCKED] Không đọc được file state: {exc}")
        return 2
    if not isinstance(state, dict) or not isinstance(state.get("transfer"), dict) or not isinstance(state.get("income"), dict):
        print("[BLOCKED] File state không có cấu trúc transfer/income hợp lệ.")
        return 2
    if str(state.get("ownerEmail", "")).casefold() != email.casefold():
        print("[BLOCKED] Email hiện tại không khớp ownerEmail trong file state; dừng để tránh kiểm tra nhầm dữ liệu.")
        return 2

    try:
        token = login(email, password)
        accounts = get_list(token, "/api/tai-khoan")
        transfers = get_list(token, "/api/chuyen-khoan")
        transactions = get_list(token, "/api/giao-dich")
    except RuntimeError as exc:
        print(f"[BLOCKED] {exc}")
        return 2

    results = []
    transfer_payload = state["transfer"].get("payload", {})
    income_payload = state["income"].get("payload", {})
    if not isinstance(transfer_payload, dict) or not isinstance(income_payload, dict):
        print("[BLOCKED] Payload trong file state không hợp lệ.")
        return 2

    results.append(check_test_row(
        "Chuyển tiền đã lưu đúng một lần", transfers, transfer_payload, "chuyenKhoanId",
        compare_fields=("tkNguonId", "tkDichId", "soTien", "moTa")))
    results.append(check_test_row(
        "Khoản thu đã lưu đúng một lần", transactions, income_payload, "giaoDichId",
        compare_fields=("tkId", "danhMucId", "loaiGd", "soTien", "moTa")))

    account_by_id = {str(row.get("tkId")): row for row in accounts if row.get("tkId") is not None}
    print("\nSố dư tài khoản hiện tại:")
    for account_id in sorted({str(transfer_payload.get("tkNguonId")), str(transfer_payload.get("tkDichId")), str(income_payload.get("tkId"))}):
        account = account_by_id.get(account_id)
        if account is None:
            print(f"[FAIL] Không tìm thấy tài khoản #{account_id} trong GET /api/tai-khoan.")
            results.append(False)
            continue
        print(f"  ID={account_id} | {account.get('tenTk', 'Tài khoản')} | số dư={account.get('soDuHienTai')} {account.get('donViTienTe', 'VND')}")

    for account_id, expected in args.check_balance:
        account = account_by_id.get(account_id)
        if account is None:
            print(f"[FAIL] Kiểm tra số dư: không tìm thấy tài khoản #{account_id}.")
            results.append(False)
            continue
        actual = money(account.get("soDuHienTai"))
        if actual == expected:
            print(f"[PASS] Số dư tài khoản #{account_id} đúng kỳ vọng: {expected}.")
            results.append(True)
        else:
            print(f"[FAIL] Số dư tài khoản #{account_id}: thực tế={actual}, kỳ vọng={expected}.")
            results.append(False)

    passed = sum(results)
    failed = len(results) - passed
    print(f"\nKết quả audit: {passed} PASS; {failed} FAIL.")
    print("Lưu ý: API có thể chỉ trả lịch sử gần nhất; nếu báo 0 bản ghi, kiểm tra DB và giới hạn lịch sử trước khi kết luận.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
