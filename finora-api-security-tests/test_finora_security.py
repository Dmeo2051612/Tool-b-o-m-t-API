"""Read-only security smoke tests for Finora endpoints behind Flask Gateway.

Only GET and OPTIONS requests are sent. No account, transaction, category, or
budget data is created, changed, or deleted.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FINORA_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
ALLOWED_ORIGIN = os.getenv("FINORA_ALLOWED_ORIGIN", "http://localhost:8080")
DISALLOWED_ORIGIN = os.getenv("FINORA_DISALLOWED_ORIGIN", "http://example.invalid")
TIMEOUT_SECONDS = 8


def send(method: str, path: str, *, token: str | None = None,
         origin: str | None = None, requested_method: str | None = None,
         requested_headers: str | None = None):
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if requested_method:
        headers["Access-Control-Request-Method"] = requested_method
    if requested_headers:
        headers["Access-Control-Request-Headers"] = requested_headers
    req = Request(f"{BASE_URL}{path}", headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            status, response_headers, raw = response.status, response.headers, response.read()
    except HTTPError as exc:
        status, response_headers, raw = exc.code, exc.headers, exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Không kết nối được Gateway tại {BASE_URL}: {exc}") from exc
    raw_text = raw.decode("utf-8", errors="replace") if raw else ""
    try:
        body = json.loads(raw_text) if raw_text else None
    except json.JSONDecodeError:
        body = raw_text
    return status, response_headers, body


class Tests:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, ok: bool, details: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}" + (f" — {details}" if details else ""))

    def run(self) -> int:
        today = date.today()
        first_day = today.replace(day=1).isoformat()
        query = urlencode({"tuNgay": first_day, "denNgay": today.isoformat()})
        protected = [
            ("Danh sách tài khoản", "/api/tai-khoan"),
            ("Danh mục", "/api/danh-muc"),
            ("Lịch sử thu/chi", "/api/giao-dich"),
            ("Lịch sử chuyển tiền", "/api/chuyen-khoan"),
            ("Ngân sách", "/api/ngan-sach"),
            ("Thống kê theo ngày", "/api/thong-ke/theo-ngay"),
            ("Thống kê tổng quan", f"/api/thong-ke/tong-quan?{query}"),
        ]
        print(f"Finora read-only security checks: {BASE_URL}\n")

        status, headers, body = send("GET", "/healthz")
        self.check(
            "Gateway health sẵn sàng",
            status == 200 and isinstance(body, dict) and body.get("status") == "ok",
            f"HTTP {status}; body={body!r}",
        )

        # Each protected read endpoint must reject anonymous and malformed JWT requests.
        for label, path in protected:
            status, _, _ = send("GET", path)
            self.check(f"{label}: từ chối khi không có JWT", status in (401, 403), f"HTTP {status}")

        malformed = "not.a.valid.jwt"
        for label, path in protected:
            status, _, _ = send("GET", path, token=malformed)
            self.check(f"{label}: từ chối JWT không hợp lệ", status in (401, 403), f"HTTP {status}")

        status, headers, _ = send(
            "OPTIONS", "/api/chuyen-khoan", origin=ALLOWED_ORIGIN,
            requested_method="POST",
            requested_headers="authorization,content-type,idempotency-key",
        )
        allow_origin = headers.get("Access-Control-Allow-Origin")
        allow_methods = (headers.get("Access-Control-Allow-Methods") or "").upper()
        allow_headers = (headers.get("Access-Control-Allow-Headers") or "").lower()
        self.check(
            "CORS preflight cho phép frontend gửi chuyển tiền",
            status in (200, 204)
            and allow_origin == ALLOWED_ORIGIN
            and "POST" in allow_methods
            and "authorization" in allow_headers
            and "content-type" in allow_headers
            and "idempotency-key" in allow_headers,
            f"HTTP {status}; origin={allow_origin!r}; methods={allow_methods!r}; headers={allow_headers!r}",
        )

        status, headers, _ = send(
            "OPTIONS", "/api/chuyen-khoan", origin=DISALLOWED_ORIGIN,
            requested_method="POST",
            requested_headers="authorization,content-type,idempotency-key",
        )
        self.check(
            "CORS không cấp quyền cho origin lạ",
            status in (200, 204) and headers.get("Access-Control-Allow-Origin") != DISALLOWED_ORIGIN,
            f"HTTP {status}; allow-origin={headers.get('Access-Control-Allow-Origin')!r}",
        )

        # Errors produced by the gateway should also retain baseline security headers.
        status, headers, _ = send("GET", "/api/tai-khoan")
        self.check(
            "Security headers vẫn có trên phản hồi lỗi xác thực",
            headers.get("X-Content-Type-Options") == "nosniff"
            and headers.get("X-Frame-Options") == "DENY",
            f"HTTP {status}; X-Content-Type-Options={headers.get('X-Content-Type-Options')!r}; X-Frame-Options={headers.get('X-Frame-Options')!r}",
        )

        total = self.passed + self.failed
        print(f"\nKết quả: {self.passed}/{total} PASS; {self.failed} FAIL")
        print("Các request chỉ dùng GET/OPTIONS; không ghi dữ liệu tài chính.")
        return 0 if self.failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(Tests().run())
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(2)
