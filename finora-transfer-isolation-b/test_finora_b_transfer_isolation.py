"""Finora B-owned transfer isolation marker test.

Read-only by default. A single 1.00 VND transfer is only submitted with:
--create-transfer, FINORA_ALLOW_TRANSFER_WRITE=YES, and exact terminal confirmation.
The state file preserves the same idempotency key/payload across retries.
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
STATE_PATH = Path(__file__).with_name("finora_user_b_transfer_isolation_state.json")
CONFIRMATION = "CREATE ONE 1 VND TEST TRANSFER FOR B"


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
    request = Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw, status = response.read(), response.status
    except HTTPError as exc:
        raw, status = exc.read(), exc.code
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{method} {path}: không kết nối được ({type(exc).__name__}); giữ file state nếu đã có.") from exc
    decoded = raw.decode("utf-8", errors="replace")
    try:
        parsed: Any = json.loads(decoded) if decoded else None
    except json.JSONDecodeError:
        parsed = decoded
    return status, parsed


def login(label: str, email_env: str, password_env: str) -> tuple[str, str]:
    email = os.getenv(email_env, "").strip()
    password = os.getenv(password_env, "")
    if not email or not password:
        raise RuntimeError(f"Cần đặt {email_env} và {password_env} trong PowerShell.")
    status, body = api_request("POST", "/api/auth/login", body={"email": email, "matKhau": password})
    if not 200 <= status < 300:
        raise RuntimeError(f"Đăng nhập người dùng {label} thất bại: HTTP {status}.")
    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Đăng nhập người dùng {label}: response thiếu accessToken.")
    say("PASS", f"Đăng nhập người dùng {label} ({email}).")
    return email, token


def get_list(token: str, path: str, label: str) -> list[dict[str, Any]]:
    status, body = api_request("GET", path, token=token)
    if not 200 <= status < 300:
        raise RuntimeError(f"{label}: GET {path} trả HTTP {status}.")
    if not isinstance(body, list) or any(not isinstance(row, dict) for row in body):
        raise RuntimeError(f"{label}: GET {path} không trả danh sách object JSON.")
    return body


def save_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def load_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không đọc được {STATE_PATH.name}; không tự tạo key mới.") from exc
    if not isinstance(value, dict) or not all(k in value for k in ("ownerEmail", "key", "payload")):
        raise RuntimeError(f"{STATE_PATH.name} sai định dạng; dừng an toàn.")
    if not isinstance(value.get("payload"), dict) or not value.get("key"):
        raise RuntimeError(f"{STATE_PATH.name} thiếu key/payload; dừng an toàn.")
    return value


def account_map(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("tkId")): row for row in accounts if row.get("tkId") is not None}


def show_accounts(accounts: list[dict[str, Any]]) -> None:
    print("\nTài khoản hiện có của B:")
    if not accounts:
        print("  (không có tài khoản nào trả về từ API)")
    for row in accounts:
        print(
            f"  ID={row.get('tkId')} | {row.get('tenTk', 'Tài khoản')} | "
            f"số dư={row.get('soDuHienTai')} | tiền tệ={row.get('donViTienTe', 'VND')}"
        )


def audit_marker(token_a: str, token_b: str, state: dict[str, Any]) -> tuple[int, int, int]:
    description = str(state.get("payload", {}).get("moTa", ""))
    if not description:
        raise RuntimeError("State không có mô tả marker moTa.")
    a_rows = get_list(token_a, "/api/chuyen-khoan", "A")
    b_rows = get_list(token_b, "/api/chuyen-khoan", "B")
    found_a = [row for row in a_rows if str(row.get("moTa", "")) == description]
    found_b = [row for row in b_rows if str(row.get("moTa", "")) == description]
    if len(found_b) == 1 and len(found_a) == 0:
        transfer_id = found_b[0].get("chuyenKhoanId")
        state["transferId"] = transfer_id
        save_state(state)
        say("PASS", f"Marker chuyển tiền của B xuất hiện đúng 1 lần ở B và 0 lần ở A (chuyenKhoanId=#{transfer_id}).")
        return 1, 0, 0
    if found_a:
        say("FAIL", f"Marker chuyển tiền của B xuất hiện trong lịch sử A ({len(found_a)} bản ghi): nguy cơ lộ dữ liệu.")
        return 0, 1, 0
    if len(found_b) > 1:
        say("FAIL", f"Marker xuất hiện {len(found_b)} lần ở B; kiểm tra dữ liệu vì có thể đã ghi trùng.")
        return 0, 1, 0
    say("BLOCKED", "Không tìm thấy marker trong lịch sử B. API có thể giới hạn lịch sử; kiểm tra phản hồi/API/DB trước khi kết luận.")
    return 0, 0, 1


def choose_account(accounts_by_id: dict[str, dict[str, Any]], prompt: str) -> str:
    value = input(prompt).strip()
    if value not in accounts_by_id:
        raise RuntimeError(f"ID '{value}' không nằm trong danh sách tài khoản B vừa lấy từ API; chưa gửi POST.")
    name = str(accounts_by_id[value].get("tenTk", ""))
    if "test" not in name.casefold():
        raise RuntimeError(f"Tài khoản #{value} không có chữ TEST trong tên; từ chối dùng tài khoản này.")
    return value


def create_or_reuse_state(email_b: str, accounts: list[dict[str, Any]]) -> dict[str, Any]:
    state = load_state()
    by_id = account_map(accounts)
    if state is not None:
        if str(state.get("ownerEmail", "")).casefold() != email_b.casefold():
            raise RuntimeError("File state thuộc người dùng B khác; không dùng lại để tránh ghi nhầm.")
        payload = state.get("payload", {})
        source_id = str(payload.get("tkNguonId"))
        destination_id = str(payload.get("tkDichId"))
        if source_id not in by_id or destination_id not in by_id:
            raise RuntimeError("Tài khoản trong state không còn xuất hiện trong danh sách của B; dừng an toàn.")
        say("INFO", f"Dùng lại key/payload đã lưu trong {STATE_PATH.name}; không tạo key mới.")
        return state

    test_accounts = {key: row for key, row in by_id.items() if "test" in str(row.get("tenTk", "")).casefold()}
    if len(test_accounts) < 2:
        raise RuntimeError("B cần ít nhất hai tài khoản có tên chứa TEST; chưa gửi POST.")
    print("\nChọn hai tài khoản TEST thuộc B (không dùng tài khoản nghiệp vụ).")
    source_id = choose_account(by_id, "Nhập ID tài khoản TEST nguồn: ")
    destination_id = choose_account(by_id, "Nhập ID tài khoản TEST đích: ")
    if source_id == destination_id:
        raise RuntimeError("Tài khoản nguồn và đích phải khác nhau; chưa gửi POST.")
    source = by_id[source_id]
    destination = by_id[destination_id]
    currency_source = str(source.get("donViTienTe") or "VND").upper()
    currency_dest = str(destination.get("donViTienTe") or "VND").upper()
    if currency_source != currency_dest:
        raise RuntimeError("Hai tài khoản phải cùng đơn vị tiền tệ; chưa gửi POST.")
    try:
        balance = float(source.get("soDuHienTai"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Không đọc được số dư tài khoản nguồn; chưa gửi POST.") from exc
    if balance < 1.00:
        raise RuntimeError("Tài khoản nguồn cần có ít nhất 1.00 VND; chưa gửi POST.")

    description = f"Finora transfer isolation marker B {uuid.uuid4().hex[:12]}"
    payload = {
        "tkNguonId": int(source_id),
        "tkDichId": int(destination_id),
        "soTien": 1.00,
        "moTa": description,
    }
    state = {
        "ownerEmail": email_b,
        "createdAt": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "key": str(uuid.uuid4()),
        "payload": payload,
    }
    save_state(state)  # persist idempotency key and payload before first write
    say("INFO", f"Đã lưu key/payload trước khi POST vào {STATE_PATH.name}.")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Finora B transfer isolation audit; GET-only by default.")
    parser.add_argument("--create-transfer", action="store_true", help="tạo đúng một chuyển khoản TEST 1 VND giữa hai tài khoản B")
    args = parser.parse_args()

    print(f"Finora B transfer isolation marker: {BASE_URL}")
    print("Mặc định chỉ đăng nhập và GET. Ghi dữ liệu cần --create-transfer, FINORA_ALLOW_TRANSFER_WRITE=YES và xác nhận tương tác.")
    try:
        email_a, token_a = login("A", "FINORA_EMAIL", "FINORA_PASSWORD")
        email_b, token_b = login("B", "FINORA_SECOND_EMAIL", "FINORA_SECOND_PASSWORD")
        if email_a.casefold() == email_b.casefold():
            raise RuntimeError("A và B phải là hai người dùng khác nhau.")
        accounts_b = get_list(token_b, "/api/tai-khoan", "B")
        transfers_a = get_list(token_a, "/api/chuyen-khoan", "A")
        transfers_b = get_list(token_b, "/api/chuyen-khoan", "B")
        say("PASS", f"Đọc được tài khoản B: {len(accounts_b)}; lịch sử chuyển tiền A={len(transfers_a)}, B={len(transfers_b)}.")
        show_accounts(accounts_b)

        if not args.create_transfer:
            state = load_state()
            if state is None:
                print("\n[INFO] Chưa có state marker. Chưa gửi POST và chưa thực hiện kiểm tra chuyển tiền B → A.")
                print("Để tạo một chuyển khoản TEST, bật FINORA_ALLOW_TRANSFER_WRITE=YES và chạy --create-transfer.")
                return 0
            if str(state.get("ownerEmail", "")).casefold() != email_b.casefold():
                raise RuntimeError("File state không thuộc người dùng B hiện tại; dừng an toàn.")
            passed, failed, blocked = audit_marker(token_a, token_b, state)
            print(f"\nKết quả audit chuyển tiền B→A: {passed} PASS; {failed} FAIL; {blocked} BLOCKED.")
            return 1 if failed else (2 if blocked else 0)

        if os.getenv("FINORA_ALLOW_TRANSFER_WRITE", "").strip() != "YES":
            raise RuntimeError("Bị chặn: cần đặt $env:FINORA_ALLOW_TRANSFER_WRITE = 'YES'.")
        if not sys.stdin.isatty():
            raise RuntimeError("Cần terminal tương tác để xác nhận trước khi ghi.")
        confirmation = input(f'\nGõ chính xác "{CONFIRMATION}" để cho phép kiểm thử ghi: ').strip()
        if confirmation != CONFIRMATION:
            say("BLOCKED", "Xác nhận không khớp; chưa gửi POST.")
            return 2

        preexisting_state = load_state()
        state = create_or_reuse_state(email_b, accounts_b)
        payload = state["payload"]
        # Validate owner and ownership of both account IDs before any write, including reused state.
        by_id = account_map(accounts_b)
        source_id, destination_id = str(payload.get("tkNguonId")), str(payload.get("tkDichId"))
        if source_id not in by_id or destination_id not in by_id:
            raise RuntimeError("Tài khoản trong payload không thuộc danh sách tài khoản B; chưa gửi POST.")
        if source_id == destination_id:
            raise RuntimeError("Payload có tài khoản nguồn và đích giống nhau; chưa gửi POST.")
        if "test" not in str(by_id[source_id].get("tenTk", "")).casefold() or "test" not in str(by_id[destination_id].get("tenTk", "")).casefold():
            raise RuntimeError("Payload phải sử dụng hai tài khoản có tên chứa TEST; chưa gửi POST.")
        # Only check current balance before the first-ever write. If state already
        # exists, a previous request may have succeeded while its response was lost;
        # retries must reuse the same key/payload even if the source balance is now lower.
        if preexisting_state is None and float(by_id[source_id].get("soDuHienTai", 0)) < float(payload.get("soTien", 0)):
            raise RuntimeError("Số dư hiện tại không đủ cho payload đã lưu. Không thay đổi payload/key; kiểm tra trước khi tiếp tục.")
        if float(payload.get("soTien", 0)) != 1.0:
            raise RuntimeError("Payload state phải là chuyển khoản đúng 1.00 VND; chưa gửi POST.")

        status, body = api_request("POST", "/api/chuyen-khoan", token=token_b, body=payload, idempotency_key=str(state["key"]))
        if not 200 <= status < 300:
            say("FAIL", f"POST chuyển tiền trả HTTP {status}; giữ nguyên state/key để điều tra, response={body}")
            return 1
        if isinstance(body, dict) and body.get("chuyenKhoanId") is not None:
            state["transferId"] = body["chuyenKhoanId"]
            save_state(state)
            say("PASS", f"API chấp nhận chuyển khoản TEST, chuyenKhoanId=#{state['transferId']}.")
        else:
            say("INFO", "POST thành công nhưng response thiếu chuyenKhoanId; sẽ đối chiếu bằng mô tả marker trong lịch sử.")

        passed, failed, blocked = audit_marker(token_a, token_b, state)
        print(f"\nKết quả audit chuyển tiền B→A: {passed} PASS; {failed} FAIL; {blocked} BLOCKED.")
        print(f"Giữ nguyên file state: {STATE_PATH}")
        return 1 if failed else (2 if blocked else 0)
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        say("BLOCKED", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
