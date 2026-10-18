# Finora — kiểm tra cách ly lịch sử chuyển tiền B → A

Bộ này là bước tiếp theo sau audit v5 và stats v6. Nó tập trung duy nhất vào endpoint lịch sử chuyển tiền, vì v5 cho thấy A có bản ghi chuyển tiền nhưng B chưa có.

## Chế độ mặc định: chỉ đọc

Chỉ đăng nhập và dùng GET cho `/api/tai-khoan` và `/api/chuyen-khoan`; không ghi dữ liệu:

```powershell
python .\test_finora_b_transfer_isolation.py
```

Nếu cần thiết lập thông tin đăng nhập trong PowerShell:

```powershell
$env:FINORA_EMAIL = 'demo3@example.com'
$a = Read-Host "Nhap mat khau demo3" -AsSecureString
$env:FINORA_PASSWORD = [System.Net.NetworkCredential]::new("", $a).Password

$env:FINORA_SECOND_EMAIL = 'demo4@example.com'
$b = Read-Host "Nhap mat khau demo4" -AsSecureString
$env:FINORA_SECOND_PASSWORD = [System.Net.NetworkCredential]::new("", $b).Password
```

## Kiểm thử ghi có bảo vệ

Chỉ chạy khi sẵn sàng tạo một chuyển khoản 1.00 VND giữa hai tài khoản TEST do B sở hữu. Bản ghi và thay đổi số dư sẽ giữ lại; script không xóa dữ liệu.

```powershell
$env:FINORA_ALLOW_TRANSFER_WRITE = 'YES'
python .\test_finora_b_transfer_isolation.py --create-transfer
```

Script yêu cầu gõ chính xác `CREATE ONE 1 VND TEST TRANSFER FOR B`, rồi chọn hai tài khoản thuộc danh sách API của B. Cả hai tên tài khoản phải chứa `TEST`, hai ID phải khác nhau, cùng đơn vị tiền tệ, tài khoản nguồn đủ số dư. Theo dữ liệu hiện tại, dự kiến chọn nguồn `#7` (số dư 1 VND) và đích `#6`.

Trước khi gửi POST, script lưu `finora_user_b_transfer_isolation_state.json` gồm payload và `Idempotency-Key`. Không xóa file này; khi chạy lại script dùng lại khóa/payload đã lưu thay vì tạo yêu cầu chuyển tiền mới. Nếu POST bị timeout hoặc kết quả chưa rõ, hãy giữ file state và kiểm tra trước khi thử lại.

Sau POST, script dùng GET lịch sử chuyển tiền của A và B, so khớp mô tả marker chính xác. Mong đợi một bản ghi ở B và không bản ghi nào ở A. Nếu lịch sử API bị giới hạn hoặc không thể tìm marker, script báo BLOCKED thay vì tự kết luận PASS.

Dùng Python 3.10+; chỉ standard library, không cần cài package ngoài. Chưa chạy với API thật của bạn; chạy trên máy local để xác nhận.
