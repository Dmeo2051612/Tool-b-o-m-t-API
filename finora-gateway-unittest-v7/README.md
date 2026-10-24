# Finora Flask Gateway unit tests v7

Bộ v7 giữ nguyên 31 bài kiểm thử của v6 và bổ sung 3 bài cho `normalize_origin()`:

- Cắt khoảng trắng ở đầu/cuối và chuẩn hóa scheme/hostname.
- Chuẩn hóa địa chỉ IPv6, gồm cổng HTTP mặc định và cổng không mặc định.
- Từ chối IPv6 sai định dạng và cổng vượt phạm vi.

Tổng cộng: 34 bài test.

## Cách chạy

Sao chép `test_security_middleware.py` vào cùng thư mục với `app.py`, sau đó chạy:

```powershell
python -m unittest -v test_security_middleware
```

Redis và backend được mock trong unit test. Bộ test không gọi API thật hoặc thay đổi database. Hãy chạy với mã `app.py` đang dùng; kết quả cuối cùng phải được xác nhận trên máy của bạn.
