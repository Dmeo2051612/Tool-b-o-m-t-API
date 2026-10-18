# Finora user-isolation test A → B

Kiểm tra chiều ngược lại với marker B → A vừa chạy: một khoản thu TEST thuộc A phải xuất hiện đúng một lần trong lịch sử A và không xuất hiện trong lịch sử B.

## Mặc định an toàn

Chạy mặc định chỉ đăng nhập và GET, không tạo giao dịch:

```powershell
python .\test_finora_user_a_isolation_marker.py
```

Cần có hai tài khoản test khác nhau. Thiết lập biến môi trường trong PowerShell nếu chưa có:

```powershell
$env:FINORA_EMAIL = 'demo3@example.com'
$a = Read-Host "Nhap mat khau demo3" -AsSecureString
$env:FINORA_PASSWORD = [System.Net.NetworkCredential]::new("", $a).Password

$env:FINORA_SECOND_EMAIL = 'demo4@example.com'
$b = Read-Host "Nhap mat khau demo4" -AsSecureString
$env:FINORA_SECOND_PASSWORD = [System.Net.NetworkCredential]::new("", $b).Password
```

## Bật kiểm thử ghi (chỉ khi đã sẵn sàng)

Thao tác sẽ thêm đúng một khoản thu 1.00 VND vào tài khoản TEST do bạn chọn thuộc A. Bản ghi không tự bị xóa. Script chỉ ghi khi đủ cả 3 điều kiện: tham số `--create-marker`, biến `FINORA_ALLOW_ISOLATION_WRITE=YES`, và xác nhận tương tác đúng nguyên văn.

```powershell
$env:FINORA_ALLOW_ISOLATION_WRITE = 'YES'
python .\test_finora_user_a_isolation_marker.py --create-marker
```

Khi được hỏi, nhập chính xác:

```text
CREATE ONE 1 VND TEST INCOME FOR A
```

Sau đó chọn một `tkId` và `danhMucId` thu nhập trong danh sách API của A. Script lưu khóa và payload vào `finora_user_a_isolation_state.json` trước khi gửi POST; không xóa state và không tự sinh khóa mới khi state đã có. Chạy lại sẽ dùng key/payload cũ, không chủ động tạo marker mới.

## Kết quả kỳ vọng

```text
[PASS] Marker của A xuất hiện đúng 1 lần trong lịch sử A và 0 lần ở B
Kết quả kiểm tra marker A→B: 1 PASS; 0 FAIL; 0 BLOCKED
```

Nếu marker không được tìm thấy, script báo `BLOCKED` thay vì kết luận cách ly đạt, vì endpoint có thể giới hạn số bản ghi lịch sử. Script dùng Python standard library, không cần cài package ngoài.
