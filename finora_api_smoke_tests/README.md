# Finora API smoke tests (read-only)

Bộ kiểm thử này xác minh đường đi `Frontend -> Flask Gateway -> ASP.NET Core -> MySQL` bằng các endpoint đang được frontend gọi. Nó chỉ đăng nhập và gửi các request `GET`; không tạo, sửa hay xóa tài khoản/giao dịch/ngân sách.

## 1. Điều kiện

- Flask Gateway đang chạy tại `http://127.0.0.1:8081` (hoặc đặt `FINORA_BASE_URL`).
- Backend C# và Redis đang chạy.
- Có một tài khoản dùng để kiểm thử.
- Python 3.10+; script dùng thư viện chuẩn, không cần cài package bằng pip.

## 2. Chạy trên Windows PowerShell

Mở PowerShell tại thư mục có `test_finora_api.py`, sau đó đặt credentials trong phiên PowerShell hiện tại:

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "email-test-cua-ban@example.com"
$env:FINORA_PASSWORD = "mat-khau-test"
python .\test_finora_api.py
```

Thay email và mật khẩu ví dụ bằng tài khoản kiểm thử thực tế. Không ghi mật khẩu vào file hoặc commit nó lên Git.

Nếu muốn kiểm tra cách ly dữ liệu giữa hai người dùng, đặt thêm:

```powershell
$env:FINORA_SECOND_EMAIL = "email-kiem-tra-thu-hai@example.com"
$env:FINORA_SECOND_PASSWORD = "mat-khau-kiem-tra-thu-hai"
python .\test_finora_api.py
```

Hai tài khoản phải khác nhau. Bài kiểm tra bổ sung này chỉ đọc danh sách tài khoản của mỗi người và kiểm tra ID không bị trộn lẫn.

## 3. Các kiểm tra

- Gateway health và kết nối Redis.
- Security headers.
- API tài khoản không chấp nhận request không có JWT.
- Đăng nhập trả về `accessToken`.
- Các API danh sách tài khoản, danh mục, thu/chi, chuyển tiền, ngân sách và thống kê theo ngày.
- Thống kê tổng quan trả về các trường frontend dùng.
- CORS cho `http://localhost:8080`.
- Tùy chọn kiểm tra danh sách tài khoản giữa hai người dùng.

## 4. Giới hạn

Đây là smoke test tích hợp chỉ đọc, không thay thế unit test của service và không kiểm thử chuyển tiền đồng thời/idempotency bằng cách ghi dữ liệu. Nếu một endpoint chưa triển khai hoặc DTO khác với contract hiện tại, test sẽ báo lỗi cụ thể để có thể điều tra.
