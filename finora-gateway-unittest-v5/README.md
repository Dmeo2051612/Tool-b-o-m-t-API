# Finora Flask Gateway — Unit Test v5

Bộ test mở rộng từ v4, tập trung vào CORS khi cấu hình nhiều origin được phép.

## Cách chạy

Đặt `test_security_middleware.py` cạnh `app.py` trong `D:\UTE\GIT\Tool sec`, sau đó chạy:

```powershell
python -m unittest -v test_security_middleware
```

## Các kiểm tra thêm trong v5

- Origin thứ hai trong allowlist được phản hồi chính xác trong `Access-Control-Allow-Origin`.
- Khi có nhiều origin được phép, phản hồi CORS có `Vary: Origin` để cache không dùng nhầm phản hồi giữa các origin.
- Origin không được phép không nhận `Access-Control-Allow-Origin` trỏ về origin đó.

Bộ test cấu hình `ALLOWED_ORIGINS` thành hai origin thử nghiệm trước khi import `app`. Redis và backend đều được mock; không gọi API thật, không ghi database và không tạo giao dịch.

Lưu ý: đây là unit test của cấu hình Flask-CORS/middleware; việc cấu hình production cần kiểm tra biến môi trường thực tế khi triển khai.
