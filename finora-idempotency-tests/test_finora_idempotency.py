"""Finora API idempotency integration tests.

Default mode is read-only. Write tests require --run-write-tests, an explicit
environment opt-in, a terminal confirmation, and user-selected test records.
Keep finora_idempotency_test_state.json so reruns reuse the same keys/payloads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = float(os.getenv("FINORA_TIMEOUT", "10"))
STATE_PATH = Path(__file__).with_name("finora_idempotency_test_state.json")


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
            raw = response.read()
            status = response.status
    except HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{method} {path}: không kết nối được ({type(exc).__name__})") from exc

    text = raw.decode("utf-8", errors="replace")
    try:
        parsed: Any = json.loads(text) if text else None
    except json.JSONDecodeError:
        parsed = text
    return status, parsed


def login() -> str:
    email = os.getenv("FINORA_EMAIL", "").strip()
    password = os.getenv("FINORA_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("Cần đặt FINORA_EMAIL và FINORA_PASSWORD trong PowerShell.")
    status, body = api_request(
        "POST", "/api/auth/login", body={"email": email, "matKhau": password}
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"Đăng nhập thất bại: HTTP {status}")
    token = body.get("accessToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("API đăng nhập không trả về accessToken hợp lệ.")
    say("PASS", f"Đăng nhập người dùng test ({email})")
    return token


def get_list(token: str, path: str) -> list[dict[str, Any]]:
    status, body = api_request("GET", path, token=token)
    if not 200 <= status < 300:
        raise RuntimeError(f"GET {path} thất bại: HTTP {status}")
    if not isinstance(body, list) or any(not isinstance(row, dict) for row in body):
        raise RuntimeError(f"GET {path}: response không phải danh sách JSON object.")
    return body


def show_test_data(accounts: list[dict[str, Any]], categories: list[dict[str, Any]]) -> None:
    print("\nTài khoản đang hoạt động (chọn các tài khoản TEST riêng):")
    if not accounts:
        print("  (chưa có tài khoản)")
    for row in accounts:
        print(
            f"  ID={row.get('tkId')} | {row.get('tenTk', 'Tài khoản')} | "
            f"Số dư={row.get('soDuHienTai')} | Tiền tệ={row.get('donViTienTe', 'VND')}"
        )
    income_categories = [
        row for row in categories
        if str(row.get("loaiGd", "")).strip().lower() == "thu"
    ]
    print("\nDanh mục thu nhập:")
    if not income_categories:
        print("  (chưa có danh mục thu nhập)")
    for row in income_categories:
        print(f"  ID={row.get('danhMucId')} | {row.get('tenDanhMuc', 'Danh mục thu')}")


def save_state(state: dict[str, Any]) -> None:
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE_PATH)


def load_or_create_state(
    accounts: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    owner_email: str,
) -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"File trạng thái {STATE_PATH.name} không đọc được. "
                "Không tự tạo khóa mới để tránh tạo giao dịch trùng ngoài ý muốn."
            ) from exc
        if not isinstance(state, dict) or not all(
            key in state for key in ("transfer", "income")
        ):
            raise RuntimeError("File trạng thái không đúng định dạng; dừng để tránh ghi dữ liệu ngoài ý muốn.")
        if str(state.get("ownerEmail", "")).casefold() != owner_email.casefold():
            raise RuntimeError(
                "File state thuộc email người dùng khác hoặc chưa có ownerEmail. "
                "Không chạy tiếp bằng state này để tránh gửi yêu cầu lên nhầm dữ liệu."
            )
        account_ids = {str(row.get("tkId")) for row in accounts if row.get("tkId") is not None}
        category_ids = {str(row.get("danhMucId")) for row in categories if row.get("danhMucId") is not None}
        transfer_payload = state.get("transfer", {}).get("payload", {})
        income_payload = state.get("income", {}).get("payload", {})
        if str(transfer_payload.get("tkNguonId")) not in account_ids or str(transfer_payload.get("tkDichId")) not in account_ids:
            raise RuntimeError("Tài khoản trong file state không còn xuất hiện trong tài khoản của người dùng; dừng an toàn.")
        if str(income_payload.get("tkId")) not in account_ids or str(income_payload.get("danhMucId")) not in category_ids:
            raise RuntimeError("Tài khoản/danh mục trong file state không còn thuộc danh sách hiện tại; dừng an toàn.")
        say("INFO", f"Dùng lại Idempotency-Key đã lưu trong {STATE_PATH.name}; không tự sinh khóa mới.")
        return state

    show_test_data(accounts, categories)
    print("\nChỉ chọn TÀI KHOẢN TEST. Test sẽ chuyển 1.00 VND và ghi một khoản thu 1.00 VND.")
    print("Các bản ghi test sẽ được giữ trong database; script không xóa chúng.")

    account_by_id = {str(row.get("tkId")): row for row in accounts if row.get("tkId") is not None}
    income_categories = [
        row for row in categories
        if str(row.get("loaiGd", "")).strip().lower() == "thu"
        and row.get("danhMucId") is not None
    ]
    if len(account_by_id) < 2:
        raise RuntimeError("Cần ít nhất hai tài khoản test đang hoạt động trước khi có thể kiểm thử chuyển tiền.")
    if not income_categories:
        raise RuntimeError("Cần có ít nhất một danh mục thu nhập test trước khi kiểm thử giao dịch thu.")

    def ask_id(prompt: str, allowed: set[str]) -> str:
        value = input(prompt).strip()
        if value not in allowed:
            raise RuntimeError(f"ID '{value}' không nằm trong danh sách vừa lấy từ API.")
        return value

    source_id = ask_id("Nhập ID tài khoản TEST nguồn: ", set(account_by_id))
    destination_id = ask_id("Nhập ID tài khoản TEST đích: ", set(account_by_id))
    if source_id == destination_id:
        raise RuntimeError("Tài khoản nguồn và đích phải khác nhau.")
    source = account_by_id[source_id]
    destination = account_by_id[destination_id]
    source_currency = str(source.get("donViTienTe") or "VND").upper()
    destination_currency = str(destination.get("donViTienTe") or "VND").upper()
    if source_currency != destination_currency:
        raise RuntimeError("Hai tài khoản test phải cùng đơn vị tiền tệ.")
    try:
        source_balance = float(source.get("soDuHienTai"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Không đọc được số dư tài khoản nguồn.") from exc
    if source_balance < 1.0:
        raise RuntimeError("Tài khoản nguồn test cần có ít nhất 1.00 VND để chạy chuyển tiền.")

    income_account_id = ask_id("Nhập ID tài khoản TEST ghi khoản thu (có thể là tài khoản nguồn): ", set(account_by_id))
    category_ids = {str(row["danhMucId"]) for row in income_categories}
    income_category_id = ask_id("Nhập ID danh mục thu nhập TEST: ", category_ids)

    description_stamp = f"Finora idempotency test {uuid.uuid4().hex[:8]}"
    now_local = datetime.now().astimezone().replace(microsecond=0).isoformat()
    state = {
        "ownerEmail": owner_email,
        "createdAt": now_local,
        "transfer": {
            "key": str(uuid.uuid4()),
            "payload": {
                "tkNguonId": int(source_id),
                "tkDichId": int(destination_id),
                "soTien": 1.00,
                "moTa": f"{description_stamp} transfer",
            },
        },
        "income": {
            "key": str(uuid.uuid4()),
            "payload": {
                "tkId": int(income_account_id),
                "danhMucId": int(income_category_id),
                "loaiGd": "thu",
                "soTien": 1.00,
                "ngayGd": now_local,
                "moTa": f"{description_stamp} income",
            },
        },
    }
    save_state(state)  # persist keys before the first write to make reruns safe
    say("INFO", f"Đã lưu payload và key trước khi ghi dữ liệu vào {STATE_PATH.name}.")
    return state


def response_id(body: Any, field: str) -> str | None:
    if isinstance(body, dict) and body.get(field) is not None:
        return str(body[field])
    return None


def check_idempotent_operation(
    token: str,
    label: str,
    path: str,
    state: dict[str, Any],
    id_field: str,
    different_payload: dict[str, Any],
) -> bool:
    key = state["key"]
    payload = state["payload"]

    def send() -> tuple[int, Any]:
        return api_request("POST", path, token=token, body=payload, idempotency_key=key)

    try:
        # Simulate two clients submitting the same logical request concurrently.
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(send)
            future_two = executor.submit(send)
            result_one = future_one.result()
            result_two = future_two.result()
    except RuntimeError as exc:
        say("FAIL", f"{label}: {exc}")
        return False

    status_one, body_one = result_one
    status_two, body_two = result_two
    id_one = response_id(body_one, id_field)
    id_two = response_id(body_two, id_field)
    if not (200 <= status_one < 300 and 200 <= status_two < 300):
        say("FAIL", f"{label}: hai request cùng key trả HTTP {status_one} và {status_two}; kiểm tra log backend và cùng file state trước khi chạy lại.")
        return False
    if id_one is None or id_two is None:
        say("FAIL", f"{label}: response thiếu trường {id_field}; kiểm tra response contract của controller.")
        return False
    if id_one != id_two:
        say("FAIL", f"{label}: cùng key nhưng trả hai ID khác nhau ({id_one}, {id_two}) — nguy cơ trùng dữ liệu.")
        return False
    say("PASS", f"{label}: hai request đồng thời cùng key trả về cùng ID #{id_one}.")

    try:
        mismatch_status, mismatch_body = api_request(
            "POST", path, token=token, body=different_payload, idempotency_key=key
        )
    except RuntimeError as exc:
        say("FAIL", f"{label} payload khác: {exc}")
        return False
    if mismatch_status == 409:
        say("PASS", f"{label}: cùng key nhưng payload khác bị từ chối bằng HTTP 409.")
        return True

    say(
        "FAIL",
        f"{label}: cùng key nhưng payload khác trả HTTP {mismatch_status}, mong đợi 409. "
        "Nếu là 2xx, kiểm tra database ngay vì backend có thể đã ghi thêm một bản ghi.",
    )
    return False


def preflight(token: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accounts = get_list(token, "/api/tai-khoan")
    categories = get_list(token, "/api/danh-muc")
    say("PASS", f"Đọc được {len(accounts)} tài khoản và {len(categories)} danh mục từ API.")
    return accounts, categories


def main() -> int:
    parser = argparse.ArgumentParser(description="Finora backend idempotency tests (read-only unless explicitly enabled).")
    parser.add_argument(
        "--run-write-tests", action="store_true",
        help="Gửi POST trên tài khoản TEST; mỗi test tạo một chuyển tiền và một khoản thu tối đa, không tự xóa dữ liệu.",
    )
    args = parser.parse_args()

    print(f"Finora idempotency tests: {BASE_URL}")
    print("Mặc định chỉ GET dữ liệu. Kiểm thử ghi cần --run-write-tests và FINORA_ALLOW_WRITE_TESTS=YES.\n")
    try:
        token = login()
        accounts, categories = preflight(token)
        show_test_data(accounts, categories)

        if not args.run_write_tests:
            print("\n[INFO] Chưa gửi POST và chưa thay đổi database.")
            print("Để chạy kiểm thử ghi trên tài khoản TEST riêng:")
            print('  $env:FINORA_ALLOW_WRITE_TESTS = "YES"')
            print("  python .\\test_finora_idempotency.py --run-write-tests")
            return 0

        if os.getenv("FINORA_ALLOW_WRITE_TESTS", "").strip() != "YES":
            raise RuntimeError("Thiếu FINORA_ALLOW_WRITE_TESTS=YES; không chạy test ghi.")
        if not sys.stdin.isatty():
            raise RuntimeError("Cần chạy trong terminal tương tác để xác nhận trước khi ghi database.")

        print("\nCẢNH BÁO: test sẽ ghi một chuyển tiền 1.00 VND và một khoản thu 1.00 VND vào dữ liệu test.")
        print("Các bản ghi không tự bị xóa. File state giữ khóa để chạy lại không tạo giao dịch mới.")
        confirmation = input('Gõ chính xác "RUN ON TEST DATA" để tiếp tục: ').strip()
        if confirmation != "RUN ON TEST DATA":
            say("INFO", "Đã hủy; không gửi POST.")
            return 0

        state = load_or_create_state(
            accounts, categories, os.getenv("FINORA_EMAIL", "").strip()
        )
        transfer_payload = dict(state["transfer"]["payload"])
        transfer_mismatch = dict(transfer_payload)
        transfer_mismatch["moTa"] = str(transfer_mismatch.get("moTa") or "") + " payload-khac"

        income_payload = dict(state["income"]["payload"])
        income_mismatch = dict(income_payload)
        income_mismatch["soTien"] = 2.00 if float(income_payload["soTien"]) != 2.00 else 3.00

        results = []
        results.append(check_idempotent_operation(
            token, "Idempotency chuyển tiền", "/api/chuyen-khoan",
            state["transfer"], "chuyenKhoanId", transfer_mismatch
        ))
        # Run income test even when transfer test failed only if its response was safely understood.
        # The saved keys protect repeat submissions, but a prior FAIL should be investigated first.
        if not results[-1]:
            say("BLOCKED", "Dừng trước test thu/chi vì test chuyển tiền thất bại; giữ nguyên file state và kiểm tra database/log backend.")
            return 1

        results.append(check_idempotent_operation(
            token, "Idempotency thu/chi", "/api/giao-dich",
            state["income"], "giaoDichId", income_mismatch
        ))
        passed = sum(results)
        failed = len(results) - passed
        print(f"\nKết quả: {passed} PASS; {failed} FAIL.")
        print(f"File khóa/payload test được giữ ở: {STATE_PATH}")
        print("Không xóa file state trước khi xác nhận các yêu cầu trước đã được xử lý xong.")
        return 1 if failed else 0
    except RuntimeError as exc:
        say("BLOCKED", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
