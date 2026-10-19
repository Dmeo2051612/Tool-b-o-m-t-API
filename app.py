
import os
import hashlib
import ipaddress
from urllib.parse import urlsplit

import redis
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config["DEBUG"] = False

TRUSTED_X_FOR_COUNT = max(
    0, int(os.getenv("TRUSTED_X_FOR_COUNT", "0"))
)
TRUSTED_X_PROTO_COUNT = max(
    0, int(os.getenv("TRUSTED_X_PROTO_COUNT", "0"))
)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=TRUSTED_X_FOR_COUNT,
    x_proto=TRUSTED_X_PROTO_COUNT
)

BACKEND_URL = os.getenv(
    "BACKEND_URL", "http://127.0.0.1:5001"
).rstrip("/")

parsed_backend = urlsplit(BACKEND_URL)

if (
    parsed_backend.scheme not in {"http", "https"}
    or not parsed_backend.netloc
    or parsed_backend.username is not None
    or parsed_backend.password is not None
    or parsed_backend.path not in {"", "/"}
    or parsed_backend.query
    or parsed_backend.fragment
):
    raise RuntimeError(
        "BACKEND_URL phải là địa chỉ gốc hợp lệ của backend."
    )

REDIS_URL = os.getenv(
    "REDIS_URL", "redis://localhost:6379/0"
)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
    health_check_interval=30,
    max_connections=50
)

MAX_REQUESTS = max(1, int(os.getenv("MAX_REQUESTS", "60")))
TIME_WINDOW = max(1, int(os.getenv("TIME_WINDOW", "10")))
AUTH_MAX_REQUESTS = max(1, int(os.getenv("AUTH_MAX_REQUESTS", "5")))
AUTH_TIME_WINDOW = max(1, int(os.getenv("AUTH_TIME_WINDOW", "60")))
PORT = int(os.getenv("PORT", "8081"))

API_METHODS = [
    "GET", "HEAD", "POST", "PUT", "PATCH",
    "DELETE", "OPTIONS"
]

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade"
}

RESPONSE_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {
    "content-length",
    "content-encoding",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-allow-credentials",
    "access-control-expose-headers",
    "access-control-max-age"
}


def normalize_origin(value):
    try:
        parsed = urlsplit(value.strip())

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        if not parsed.hostname:
            return None

        if parsed.username is not None or parsed.password is not None:
            return None

        if parsed.path or parsed.query or parsed.fragment:
            return None

        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower()
        port = parsed.port

        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"

        if (scheme == "http" and port == 80) or (
            scheme == "https" and port == 443
        ):
            port = None

        authority = (
            hostname if port is None
            else f"{hostname}:{port}"
        )

        return f"{scheme}://{authority}"

    except (ValueError, AttributeError):
        return None


ALLOWED_ORIGINS = {
    normalized
    for item in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:8080"
    ).split(",")
    if (normalized := normalize_origin(item)) is not None
}

if not ALLOWED_ORIGINS:
    raise RuntimeError(
        "ALLOWED_ORIGINS chưa được cấu hình hợp lệ."
    )

CORS(
    app,
    resources={
        r"/api/.*": {
            "origins": list(ALLOWED_ORIGINS),
            "methods": API_METHODS,
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "Idempotency-Key",
                "Accept"
            ],
            "expose_headers": ["Retry-After"]
        }
    }
)

RATE_LIMIT_SCRIPT = redis_client.register_script(
    """
    local current = redis.call('INCR', KEYS[1])
    local ttl = redis.call('TTL', KEYS[1])

    if ttl == -1 then
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
        ttl = tonumber(ARGV[1])
    end

    return {current, ttl}
    """
)


def hash_ip(client_ip):
    return hashlib.sha256(
        client_ip.encode("utf-8")
    ).hexdigest()


def get_client_ip():
    remote_addr = request.remote_addr

    if not remote_addr:
        return None

    try:
        return ipaddress.ip_address(remote_addr).compressed
    except ValueError:
        return None


def apply_rate_limit_for_scope(client_ip, scope, max_requests, time_window):
    """Giới hạn request theo IP và phạm vi để các nhóm endpoint không dùng chung quota."""
    redis_key = f"rate_limit:{scope}:{hash_ip(client_ip)}"

    result = RATE_LIMIT_SCRIPT(
        keys=[redis_key],
        args=[time_window]
    )

    current_count = int(result[0])
    ttl = int(result[1])

    if current_count > max_requests:
        retry_after = max(ttl, 1)

        response = jsonify({
            "error": "Too many requests.",
            "scope": scope,
            "retry_after_seconds": retry_after
        })

        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)

        return response

    return None


def apply_rate_limit(client_ip):
    # Quota chung đủ rộng cho frontend tải dashboard qua nhiều endpoint.
    response = apply_rate_limit_for_scope(
        client_ip,
        "ip",
        MAX_REQUESTS,
        TIME_WINDOW
    )
    if response is not None:
        return response

    # Đặt giới hạn riêng cho đăng nhập/đăng ký để giảm thử mật khẩu hàng loạt.
    if request.method == "POST":
        auth_scopes = {
            "/api/auth/login": "auth-login",
            "/api/auth/register": "auth-register"
        }
        scope = auth_scopes.get(request.path.rstrip("/"))
        if scope:
            return apply_rate_limit_for_scope(
                client_ip,
                scope,
                AUTH_MAX_REQUESTS,
                AUTH_TIME_WINDOW
            )

    return None


@app.before_request
def security_middleware():
    if request.path == "/healthz":
        return None

    if not (
        request.path == "/api"
        or request.path.startswith("/api/")
    ):
        return None

    # 1. Xác định IP client.
    client_ip = get_client_ip()

    if client_ip is None:
        return jsonify({
            "error": "Không xác định được địa chỉ client."
        }), 400

    # 2. Kiểm tra blacklist và Rate Limiting.
    try:
        if redis_client.sismember(
            "blacklist_ips", hash_ip(client_ip)
        ):
            return jsonify({
                "error": "Truy cập bị từ chối."
            }), 403

        rate_limit_response = apply_rate_limit(client_ip)

        if rate_limit_response is not None:
            return rate_limit_response

    except redis.RedisError as exc:
        app.logger.error(
            "Redis request failed: %s",
            type(exc).__name__
        )

        return jsonify({
            "error": "Dịch vụ bảo vệ hiện không khả dụng."
        }), 503

    # 3. Xử lý CORS preflight sau các bước bảo vệ.
    if request.method == "OPTIONS":
        return Response(status=204)

    # 4. Kiểm tra nguồn của request thay đổi dữ liệu.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")

        if origin is not None:
            origin_value = normalize_origin(origin)

            if origin_value not in ALLOWED_ORIGINS:
                return jsonify({
                    "error": "Nguồn request không được phép."
                }), 403

        if referer is not None:
            try:
                parsed_referer = urlsplit(referer)

                if (
                    parsed_referer.scheme
                    and parsed_referer.netloc
                ):
                    referer_value = normalize_origin(
                        f"{parsed_referer.scheme}://"
                        f"{parsed_referer.netloc}"
                    )
                else:
                    referer_value = None

            except ValueError:
                referer_value = None

            if referer_value not in ALLOWED_ORIGINS:
                return jsonify({
                    "error": "Nguồn request không được phép."
                }), 403

    return None


@app.route("/healthz", methods=["GET"])
def health_check():
    try:
        redis_client.ping()

        return jsonify({
            "status": "ok",
            "redis": "connected"
        }), 200

    except redis.RedisError:
        return jsonify({
            "status": "degraded",
            "redis": "unavailable"
        }), 503


def forward_to_backend():
    upstream_url = f"{BACKEND_URL}{request.path}"

    if request.query_string:
        try:
            query_string = request.query_string.decode("ascii")
        except UnicodeDecodeError:
            return jsonify({
                "error": "Query string không hợp lệ."
            }), 400

        upstream_url += f"?{query_string}"

    connection_tokens = {
        item.strip().lower()
        for item in request.headers.get(
            "Connection", ""
        ).split(",")
        if item.strip()
    }

    excluded_request_headers = HOP_BY_HOP_HEADERS | {
        "host",
        "content-length",
        "accept-encoding"
    } | connection_tokens

    upstream_headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in excluded_request_headers
        and not name.lower().startswith("x-forwarded-")
    }

    client_ip = get_client_ip()

    upstream_headers["X-Forwarded-For"] = (
        client_ip if client_ip else ""
    )
    upstream_headers["X-Forwarded-Proto"] = (
        "https" if request.is_secure else "http"
    )

    try:
        upstream_response = requests.request(
            method=request.method,
            url=upstream_url,
            headers=upstream_headers,
            data=request.get_data(),
            timeout=(3, 15),
            allow_redirects=False
        )

    except requests.Timeout:
        app.logger.warning(
            "Backend timeout. Path=%s",
            request.path
        )

        return jsonify({
            "error": "Backend không phản hồi kịp thời."
        }), 504

    except requests.RequestException as exc:
        app.logger.error(
            "Backend connection failed: %s",
            type(exc).__name__
        )

        return jsonify({
            "error": "Không thể kết nối tới backend."
        }), 502

    response = Response(
        upstream_response.content,
        status=upstream_response.status_code
    )

    for name, value in upstream_response.headers.items():
        if name.lower() not in RESPONSE_EXCLUDED_HEADERS:
            response.headers[name] = value

    return response


@app.route("/api", defaults={"path": ""}, methods=API_METHODS)
@app.route("/api/", defaults={"path": ""}, methods=API_METHODS)
@app.route("/api/<path:path>", methods=API_METHODS)
def proxy_api(path):
    return forward_to_backend()


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    response.headers["Cache-Control"] = "no-store"

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000"
        )

    return response


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=False,
        use_reloader=False
    )