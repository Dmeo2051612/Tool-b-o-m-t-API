"""Read-only smoke tests for the Finora Flask Gateway + ASP.NET Core API.

The script only logs in and performs GET requests. It does not create, update,
or delete accounts, transactions, categories, or budgets.
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
EMAIL = os.getenv("FINORA_EMAIL", "").strip()
PASSWORD = os.getenv("FINORA_PASSWORD", "")
SECOND_EMAIL = os.getenv("FINORA_SECOND_EMAIL", "").strip()
SECOND_PASSWORD = os.getenv("FINORA_SECOND_PASSWORD", "")
TIMEOUT_SECONDS = 8


def request(method: str, path: str, *, token: str | None = None,
            payload: dict | None = None, origin: str | None = None):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin

    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            response_headers = response.headers
            raw = response.read()
    except HTTPError as exc:
        status = exc.code
        response_headers = exc.headers
        raw = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Không kết nối được {BASE_URL}. Hãy kiểm tra Flask Gateway và Redis: {exc}"
        ) from exc

    text = raw.decode("utf-8", errors="replace") if raw else ""
    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        data = text
    return status, response_headers, data


class SmokeTests:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.token = None
        self.accounts = None

    def check(self, name, condition, details=""):
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}" + (f" — {details}" if details else ""))

    def run(self):
        print(f"Finora API smoke tests: {BASE_URL}")
        print("Lưu ý: bộ test này chỉ đọc dữ liệu, không tạo giao dịch hay thay đổi số dư.\n")

        # 1. Gateway health / Redis availability
        status, headers, body = request("GET", "/healthz")
        self.check(
            "Gateway health và Redis",
            status == 200 and isinstance(body, dict)
            and body.get("status") == "ok" and body.get("redis") == "connected",
            f"HTTP {status}, body={body!r}",
        )
        self.check(
            "Security headers từ Gateway",
            headers.get("X-Content-Type-Options") == "nosniff"
            and headers.get("X-Frame-Options") == "DENY",
            f"X-Content-Type-Options={headers.get('X-Content-Type-Options')!r}; "
            f"X-Frame-Options={headers.get('X-Frame-Options')!r}",
        )

        # 2. Protected endpoint must not accept anonymous callers
        status, _, body = request("GET", "/api/tai-khoan")
        self.check(
            "API tài khoản từ chối request chưa đăng nhập",
            status in (401, 403),
            f"HTTP {status}, body={body!r}",
        )

        if not EMAIL or not PASSWORD:
            print("\nChưa đặt FINORA_EMAIL và FINORA_PASSWORD nên chưa chạy các test API có xác thực.")
            print("Đặt hai biến môi trường trong PowerShell rồi chạy lại script.")
            self.failed += 1
            return self.summary()

        # 3. Login with the same body shape as the frontend.
        status, _, body = request(
            "POST", "/api/auth/login",
            payload={"email": EMAIL, "matKhau": PASSWORD},
            origin="http://localhost:8080",
        )
        token = body.get("accessToken") if isinstance(body, dict) else None
        self.check(
            "Đăng nhập trả về accessToken",
            200 <= status < 300 and isinstance(token, str) and bool(token),
            f"HTTP {status}, body={body!r}" if not token else "",
        )
        if not token:
            print("\nKhông thể tiếp tục các test có xác thực vì đăng nhập thất bại.")
            return self.summary()
        self.token = token

        # 4. Authenticated read-only APIs expected by the frontend.
        endpoints = [
            ("Danh sách tài khoản", "/api/tai-khoan"),
            ("Danh mục", "/api/danh-muc"),
            ("Lịch sử thu/chi", "/api/giao-dich"),
            ("Lịch sử chuyển tiền", "/api/chuyen-khoan"),
            ("Ngân sách", "/api/ngan-sach"),
            ("Thống kê theo ngày", "/api/thong-ke/theo-ngay"),
        ]
        for name, path in endpoints:
            status, _, body = request("GET", path, token=self.token)
            valid = 200 <= status < 300 and isinstance(body, list)
            self.check(name + " trả về danh sách JSON", valid,
                       f"HTTP {status}, kiểu phản hồi={type(body).__name__}")
            if path == "/api/tai-khoan" and valid:
                self.accounts = body

        today = date.today()
        first_day = today.replace(day=1).isoformat()
        query = urlencode({"tuNgay": first_day, "denNgay": today.isoformat()})
        status, _, body = request(
            "GET", f"/api/thong-ke/tong-quan?{query}", token=self.token
        )
        keys = {"tongThu", "tongChi", "chenhLech", "soGiaoDich"}
        self.check(
            "Thống kê tổng quan có đủ trường dữ liệu",
            200 <= status < 300 and isinstance(body, dict) and keys.issubset(body.keys()),
            f"HTTP {status}, body={body!r}",
        )

        # 5. CORS response for the configured frontend origin.
        status, headers, _ = request(
            "GET", "/api/tai-khoan", token=self.token,
            origin="http://localhost:8080",
        )
        self.check(
            "CORS cho phép frontend localhost:8080",
            200 <= status < 300
            and headers.get("Access-Control-Allow-Origin") == "http://localhost:8080",
            f"HTTP {status}, allow-origin={headers.get('Access-Control-Allow-Origin')!r}",
        )

        # 6. Optional second-user data-isolation smoke check (read only).
        if SECOND_EMAIL and SECOND_PASSWORD:
            status2, _, body2 = request(
                "POST", "/api/auth/login",
                payload={"email": SECOND_EMAIL, "matKhau": SECOND_PASSWORD},
                origin="http://localhost:8080",
            )
            token2 = body2.get("accessToken") if isinstance(body2, dict) else None
            self.check("Đăng nhập tài khoản kiểm tra thứ hai", 200 <= status2 < 300 and bool(token2),
                       f"HTTP {status2}")
            if token2:
                status2, _, accounts2 = request("GET", "/api/tai-khoan", token=token2)
                ids1 = {a.get("tkId") for a in (self.accounts or []) if isinstance(a, dict)}
                ids2 = {a.get("tkId") for a in accounts2 if isinstance(a, dict)} if isinstance(accounts2, list) else set()
                self.check(
                    "Danh sách tài khoản không lẫn giữa hai người dùng",
                    status2 == 200 and isinstance(accounts2, list) and ids1.isdisjoint(ids2),
                    f"HTTP {status2}, giao nhau={ids1.intersection(ids2)}",
                )

        return self.summary()

    def summary(self):
        total = self.passed + self.failed
        print(f"\nKết quả: {self.passed}/{total} PASS; {self.failed} FAIL")
        return 0 if self.failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(SmokeTests().run())
    except RuntimeError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(2)
