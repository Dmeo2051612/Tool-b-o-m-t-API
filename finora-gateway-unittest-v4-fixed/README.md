# Finora Flask Gateway - unit test v4 (fixed)

## Nội dung

Bộ kiểm thử gồm 25 bài `unittest`. Phiên bản này sửa lỗi đóng gói ở bản v4 trước: sáu hàm test mở rộng được đặt bên trong `SecurityMiddlewareTests`, trước khối `if __name__ == "__main__"`, nên `unittest` có thể phát hiện.

Sáu bài bổ sung kiểm tra:

- IP client không hợp lệ bị từ chối trước khi gọi Redis/backend.
- Backend timeout trả HTTP 504.
- Lỗi kết nối backend trả HTTP 502.
- Header hop-by-hop và `X-Forwarded-*` từ client không được chuyển tiếp nguyên trạng.
- Header hop-by-hop và CORS không phù hợp từ upstream được lọc.
- Health check trả 503 và `degraded` khi Redis không khả dụng.

## Cách dùng

Sao chép `test_security_middleware.py` vào cùng thư mục với `app.py`, ví dụ `D:\UTE\GIT\Tool sec\`, rồi chạy:

```powershell
python -m unittest -v test_security_middleware
```

## An toàn và giới hạn

Redis và backend được mock; test không gọi API thật, không kết nối MySQL, không tạo hoặc sửa giao dịch. Bộ test nhập `app.py` thật từ thư mục chạy nên các test xác minh hành vi source hiện có, không phải kiểm thử tích hợp hệ thống chạy thật.

File test đã được kiểm tra cú pháp và xác nhận có đúng 25 test method có thể được phát hiện bằng AST. Môi trường đóng gói không có Flask / Flask-CORS / redis-py, vì vậy chưa thực thi toàn bộ bộ test tại đây; hãy chạy ở môi trường dự án.
