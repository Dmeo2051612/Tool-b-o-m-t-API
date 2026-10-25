# Finora Gateway – Integration Regression v1

Bộ kiểm thử smoke/integration chạy trên Windows PowerShell, gọi **Gateway, Redis và C# API đang chạy thật**. Nó bổ sung cho 48 unit test mock hiện có; không thay thế bộ unit test.

## Điều kiện

- Flask Gateway đang chạy ở `http://127.0.0.1:8081`.
- Redis đang chạy và Gateway có thể kết nối Redis.
- C# API đang chạy phía sau Gateway và yêu cầu JWT với `GET /api/tai-khoan`.
- Origin frontend mặc định là `http://localhost:8080`.

Script **không gửi JWT hợp lệ, không xóa/tạo Redis key và không tạo giao dịch có thể thành công**. Nó gửi một POST với Origin không được phép và body `{}` để kiểm tra Gateway chặn trước khi chuyển tiếp. Chỉ dùng trên môi trường local/dev, không chạy với URL production.

## Chạy

Giải nén ZIP, mở PowerShell và chuyển đến thư mục chứa script. Chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\integration-regression.ps1
```

Nếu chính sách hiện tại cho phép chạy script, có thể bỏ dòng `Set-ExecutionPolicy`.

Nếu Gateway chạy ở địa chỉ khác hoặc frontend có Origin khác:

```powershell
.\integration-regression.ps1 -GatewayBaseUrl "http://127.0.0.1:8081" -AllowedOrigin "http://localhost:8080"
```

## Các kiểm tra

1. `/healthz` trả `200`, JSON có `status=ok` và `redis=connected`.
2. Preflight của Origin được phép trả `204`, có `Access-Control-Allow-Origin`, cho phép `GET` và header `Authorization`.
3. Preflight của Origin không được phép không có `Access-Control-Allow-Origin`.
4. GET `/api/tai-khoan` với Origin không được phép và không có JWT vẫn đi đến bước xác thực backend (`401`) nhưng không cấp quyền CORS.
5. POST `/api/chuyen-khoan` với Origin không được phép bị Gateway chặn (`403`).
6. Response từ chối có `X-Content-Type-Options: nosniff`.

## Đọc kết quả

- `PASS`: kết quả khớp hành vi mong đợi.
- `FAIL HTTP 502`: Gateway không kết nối được backend; kiểm tra `BACKEND_URL`.
- `FAIL HTTP 503` hoặc health check degraded: kiểm tra Redis và `REDIS_URL`.
- `FAIL HTTP 429`: có thể đã vượt rate limit trước khi chạy script. Chờ hết `TIME_WINDOW` rồi chạy lại; không xóa Redis key production chỉ để làm test pass.
- `FAIL HTTP 401` ở POST có Origin không hợp lệ: Gateway đã không chặn request ở tầng Origin như mong đợi; kiểm tra middleware trước khi tiếp tục.
- `FAIL HTTP 204` ở preflight Origin bị chặn nhưng có ACAO: kiểm tra cấu hình CORS.

Lưu ý: health check chỉ xác nhận Redis kết nối tại thời điểm kiểm tra. Script không cố ý làm Redis ngừng hoạt động và không thử vượt rate limit trên Gateway chính, nhằm tránh tác động đến phiên test đang chạy.
