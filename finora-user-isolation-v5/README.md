# Finora — audit cách ly dữ liệu người dùng v5 (chỉ đọc)

Bộ test đăng nhập bằng hai tài khoản test A/B, sau đó chỉ gọi GET. Script **không** tạo, cập nhật, chuyển hay xóa dữ liệu tài chính. `POST /api/auth/login` chỉ được dùng để đăng nhập.

## Kiểm tra

- So sánh ID từ `/api/tai-khoan`, `/api/danh-muc`, `/api/giao-dich`, `/api/chuyen-khoan`, `/api/ngan-sach` giữa A và B.
- Gọi `/api/thong-ke/theo-ngay` và `/api/thong-ke/tong-quan` cho từng người dùng để xác minh status/shape và ghi lại số liệu trả về.
- Nếu cùng một ID xuất hiện trong danh sách A và B, script báo FAIL. Nếu một endpoint chỉ có dữ liệu của một người, kết quả ghi rõ đó chỉ là kiểm tra một chiều. Nếu cả hai bên đều rỗng, endpoint bị SKIP (trừ danh sách tài khoản thì BLOCKED).

Thống kê tổng quan/theo ngày chỉ được kiểm tra response và trường bắt buộc; kết quả này không tự nó chứng minh số liệu tổng hợp được cách ly đúng. Để kiểm tra đầy đủ, cần đối chiếu thêm với các bản ghi và logic truy vấn tương ứng.

## Yêu cầu

- Python 3.10+
- `requests`
- Flask Gateway, Redis và API đang chạy

## Chạy trong PowerShell

```powershell
python -m pip install requests
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "demo3@example.com"
$env:FINORA_PASSWORD = "<mật khẩu A>"
$env:FINORA_SECOND_EMAIL = "demo4@example.com"
$env:FINORA_SECOND_PASSWORD = "<mật khẩu B>"
python .\test_finora_user_isolation.py
```

Không lưu mật khẩu vào file hoặc commit lên Git. Có thể dùng các biến môi trường đã thiết lập trong cùng cửa sổ PowerShell; không cần chạy lại `pip install` nếu `requests` đã có.

## Diễn giải hiện tại

Hai bài marker A→B và B→A có thể chạy riêng để chứng minh hai marker không lộ trong lịch sử người còn lại. Bộ v5 mở rộng so sánh ID trên 5 endpoint danh sách và kiểm tra endpoint thống kê, nhưng chỉ những endpoint có dữ liệu ở cả hai người dùng mới cho phép đối chiếu hai chiều về ID. Đây là kiểm thử tích hợp trên các dữ liệu được API trả về, không thay thế review source code hoặc kiểm thử phân quyền ở mọi tuyến API.
