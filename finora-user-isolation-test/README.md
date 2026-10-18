# Finora — kiểm tra cách ly dữ liệu giữa người dùng

Bộ test chỉ đăng nhập và gửi các request `GET`. Nó không tạo, sửa, chuyển, hoặc xóa dữ liệu tài chính.

## Yêu cầu

- Flask Gateway và backend C# đang chạy.
- Python 3.10+ và thư viện `requests` (`python -m pip install requests`).
- Hai tài khoản test khác nhau. Mỗi tài khoản cần có ít nhất một tài khoản tài chính để kiểm tra cách ly endpoint tài khoản.

## Chạy trên PowerShell

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "email-test-A@example.com"
$env:FINORA_PASSWORD = "mat-khau-test-A"
$env:FINORA_SECOND_EMAIL = "email-test-B@example.com"
$env:FINORA_SECOND_PASSWORD = "mat-khau-test-B"
python .\test_finora_user_isolation.py
```

Thay các giá trị ví dụ bằng thông tin hai tài khoản test riêng. Không lưu mật khẩu vào file hoặc commit terminal transcript có mật khẩu.

## Ý nghĩa kết quả

- `PASS`: hai người dùng nhận các ID bản ghi riêng biệt ở endpoint tương ứng.
- `FAIL`: request lỗi, phản hồi sai định dạng, tài khoản test không có tài khoản tài chính, hoặc hai người dùng nhận chung ID — cần rà soát truy vấn lọc theo `userId`.
- `SKIP`: ít nhất một trong hai người dùng chưa có dữ liệu cho endpoint đó, nên chưa đủ căn cứ kết luận về cách ly dữ liệu.

Đây là smoke test phát hiện rò rỉ rõ ràng dựa trên các danh sách và ID trả về; nó không thay thế review truy vấn backend, test theo từng ID (IDOR), hoặc kiểm thử bảo mật độc lập.
