# Finora Flask Gateway - unit test v4

## Mục đích

Mở rộng bộ unit test từ 19 lên 25 bài. Sáu bài bổ sung bao phủ:

- IP client không hợp lệ bị từ chối trước khi gọi Redis/backend.
- Backend timeout trả HTTP 504.
- Lỗi kết nối backend trả HTTP 502.
- Header hop-by-hop và header `X-Forwarded-*` do client cung cấp không được chuyển tiếp nguyên trạng.
- Header hop-by-hop và CORS do upstream trả về được lọc trước khi trả cho client.
- Health check trả 503 và trạng thái `degraded` khi Redis không khả dụng.

## Cách dùng

Giải nén ZIP. Sao chép `test_security_middleware.py` vào thư mục cùng cấp với `app.py`, ví dụ `D:\UTE\GIT\Tool sec\`:

```powershell
Copy-Item ".\finora-gateway-unittest-v4\test_security_middleware.py" ".\test_security_middleware.py" -Force
cd "D:\UTE\GIT\Tool sec"
python -m unittest -v test_security_middleware
```

Nếu bạn giải nén vào thư mục khác, hãy điều chỉnh đường dẫn nguồn cho đúng. Chạy test trong thư mục chứa `app.py` để lệnh `import app as gateway` hoạt động.

## An toàn và giới hạn

Tất cả tương tác Redis và backend trong test được mock. Test không gọi API thật, không đụng MySQL và không tạo/sửa/xóa giao dịch. Chúng xác minh các chức năng đang có trong mã Gateway; nếu sửa `app.py`, cần chạy lại toàn bộ suite.

Bộ test được soạn và kiểm tra cú pháp, nhưng chưa được chạy trong môi trường tạo file này vì không có Flask, Flask-CORS và redis-py. Hãy coi kết quả từ môi trường máy bạn là kết quả thực thi có thẩm quyền.
