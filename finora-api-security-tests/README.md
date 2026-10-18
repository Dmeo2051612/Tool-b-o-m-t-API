# Finora — kiểm thử bảo mật API (chỉ đọc)

Bộ kiểm thử này bổ sung cho `test_finora_api.py`. Nó kiểm tra các endpoint cần đăng nhập từ chối cả request không có JWT và JWT sai định dạng; kiểm tra preflight CORS cho frontend `localhost:8080`; và kiểm tra security headers trên phản hồi lỗi.

**An toàn dữ liệu:** chỉ gửi `GET` và `OPTIONS`. Không cần email/mật khẩu; không tạo, sửa hoặc xóa dữ liệu tài chính.

## Chạy trên Windows PowerShell

Mở PowerShell ở thư mục chứa `test_finora_security.py`. Có thể đặt biến URL nếu khác mặc định:

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
python .\test_finora_security.py
```

Nếu frontend được cấu hình tại một origin khác, đặt `FINORA_ALLOWED_ORIGIN`. Origin lạ dùng để thử từ chối CORS có thể đặt qua `FINORA_DISALLOWED_ORIGIN`.

## Test được thực hiện

- Gateway `/healthz` sẵn sàng.
- 7 endpoint bảo vệ từ chối request không có JWT.
- 7 endpoint bảo vệ từ chối JWT sai định dạng.
- CORS preflight cho phép `POST` và các header `Authorization`, `Content-Type`, `Idempotency-Key` từ origin được phép.
- Origin không được cho phép không nhận `Access-Control-Allow-Origin` tương ứng.
- Security headers còn có trên phản hồi lỗi xác thực.

Đây là kiểm thử smoke bảo mật, không thay thế kiểm thử phân quyền với hai tài khoản khác nhau, unit test của C# service, hay kiểm thử ghi dữ liệu cho idempotency/concurrency.
