# Finora Gateway – Integration Resilience v3

Bộ kiểm thử tích hợp cho hai hành vi chưa kiểm tra trong bộ smoke test v2:

1. Rate Limiting thật trên một tiến trình Flask tạm, cấu hình `MAX_REQUESTS=3`, `TIME_WINDOW=10`.
2. Fail-closed khi Redis không khả dụng, cũng trên một tiến trình Flask tạm riêng.

## Trước khi chạy

- Giữ Redis đang chạy tại `127.0.0.1:6379`.
- Script giả định file `app.py` của Flask Gateway nằm ở `D:\UTE\GIT\Tool sec\app.py`.
- Cổng `8082`, `8083` và `6399` phải chưa được sử dụng.
- Redis local cần hỗ trợ DB index 15 (mặc định Redis thường có DB 0–15). Nếu URL Redis của bạn khác, có thể truyền bằng `-TestRedisUrl`.
- Chạy chỉ trên máy local/dev, không chạy với URL production.

## Cách chạy

Giải nén ZIP trong `D:\UTE\GIT\Tool sec`, mở PowerShell:

```powershell
cd "D:\UTE\GIT\Tool sec\finora-gateway-integration-v3"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\integration-resilience.ps1
```

Nếu file `app.py` nằm ở nơi khác:

```powershell
.\integration-resilience.ps1 -GatewayProjectPath "D:\duong-dan\toi\thu-muc-chua-app.py"
```

Nếu cần đổi Redis URL dùng cho DB cô lập:

```powershell
.\integration-resilience.ps1 -TestRedisUrl "redis://127.0.0.1:6379/15"
```

## Script làm gì?

### A. Rate limit trên Gateway tạm ở cổng 8082

- Khởi chạy một tiến trình mới bằng `app.py`, dùng Redis DB 15, `MAX_REQUESTS=3`, `TIME_WINDOW=10`.
- Gateway tạm được cấu hình tin một giá trị `X-Forwarded-For` để dùng IP thử nghiệm riêng trong test; thiết lập này chỉ áp dụng cho tiến trình kiểm thử tạm và không nên sao chép sang cấu hình chạy chính nếu chưa có reverse proxy đáng tin cậy.
- Gửi bốn POST tới `/api/chuyen-khoan` với Origin không được phép và payload `{}`. Ba request đầu phải bị Origin guard chặn `403`; request thứ tư phải bị rate limit chặn `429`, chứng minh rate limit chạy trước Origin validation.
- Kiểm tra response `429` có `Retry-After`.
- Counter key do test tạo trong Redis DB 15 có TTL 10 giây; IP kiểm thử được tạo ngẫu nhiên. Script **không chạy `FLUSHDB`, không xóa key nào**.

### B. Fail-closed trên Gateway tạm ở cổng 8083

- Khởi chạy tiến trình thứ hai với Redis URL trỏ tới `127.0.0.1:6399`, cổng được yêu cầu phải chưa mở.
- `/healthz` phải trả `503` khi Redis không kết nối được.
- `GET /api/tai-khoan` phải trả `503`, không được bỏ qua middleware để đi tiếp tới backend.

Cuối quá trình, script tự dừng các tiến trình Gateway tạm đã khởi chạy và in đường dẫn log trong thư mục `%TEMP%\finora-gateway-integration-v3-*`. Gateway đang chạy ở cổng 8081 không bị khởi động lại hoặc thay đổi biến môi trường của nó.

## Đọc kết quả

Kết quả thông thường là **6 PASS, 0 FAIL**. Nếu startup không thành công, xem `*.stderr.log` trong đường dẫn log được script in ra. Nếu Redis DB 15 không khả dụng, script dừng phần rate-limit test thay vì xóa dữ liệu để cố làm test pass.

Chú ý: việc kiểm thử fail-closed cố ý tạo log Redis connection error trong tiến trình Gateway tạm. Đây là hành vi mong muốn trong test, không tự động có nghĩa Gateway chính đang lỗi.
