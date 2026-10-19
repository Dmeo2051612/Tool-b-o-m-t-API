# Finora — kiểm thử từ chối chuyển khoản giữa hai người dùng

## Mục tiêu
Kiểm tra API có từ chối yêu cầu chuyển tiền mà `tkNguonId` thuộc người dùng B nhưng `tkDichId` thuộc người dùng A, bất kể token đăng nhập thuộc A hay B. Sau mỗi yêu cầu bị từ chối, script đọc lại số dư và lịch sử chuyển khoản của cả hai người để xác nhận không đổi.

## An toàn
- Mặc định: chỉ POST đăng nhập; các endpoint dữ liệu chỉ dùng GET.
- Chạy ghi âm tính tiêu cực chỉ khi có đủ cả ba điều kiện: `--run-negative-write-tests`, `FINORA_ALLOW_CROSS_USER_TESTS=YES`, và xác nhận tương tác chính xác `RUN CROSS-USER NEGATIVE TESTS`.
- Script có thể gửi tối đa 2 POST chuyển tiền 1 VND tới API, với body cố tình chứa ID thuộc hai chủ sở hữu khác nhau. Nếu API có lỗi phân quyền, yêu cầu có thể bị chấp nhận hoặc gây lỗi phía server. Chỉ chạy trên dữ liệu TEST.
- Nếu phản hồi không rõ do mất kết nối, script dừng và không tự gửi lại. Giữ file state. Không xóa file state sau lỗi.
- Khi API trả về 2xx, script dừng ngay, không gửi request negative thứ hai; kiểm tra ngay số dư/lịch sử trong DB.
- Script không tự xóa và không cố khôi phục giao dịch.

## Chuẩn bị PowerShell
Cần API Gateway và backend đang chạy. Nhập thông tin qua biến môi trường; mật khẩu không được ghi vào file:

```powershell
$env:FINORA_EMAIL = 'demo3@example.com'
$a = Read-Host 'Nhap mat khau A' -AsSecureString
$env:FINORA_PASSWORD = [System.Net.NetworkCredential]::new('', $a).Password
$env:FINORA_SECOND_EMAIL = 'demo4@example.com'
$b = Read-Host 'Nhap mat khau B' -AsSecureString
$env:FINORA_SECOND_PASSWORD = [System.Net.NetworkCredential]::new('', $b).Password
```

## Bước 1 — chỉ đọc

```powershell
python .\test_finora_cross_user_transfer.py
```

Kiểm tra script đọc được tài khoản và lịch sử chuyển tiền của cả A và B. Ở chế độ này, không gửi POST chuyển tiền.

## Bước 2 — kiểm thử từ chối (chỉ trên TEST)

```powershell
$env:FINORA_ALLOW_CROSS_USER_TESTS = 'YES'
python .\test_finora_cross_user_transfer.py --run-negative-write-tests
```

Sau xác nhận, nhập ID nguồn thuộc B (ví dụ `6`, số dư cần ít nhất 1 VND) và ID đích thuộc A (ví dụ `4`). Script tạo `finora_cross_user_transfer_state.json` trước khi gửi request, giữ cùng idempotency keys khi chạy lại. Giữ file state ở nguyên chỗ.

## Diễn giải kết quả
- Kỳ vọng mỗi POST bị từ chối bằng HTTP 4xx và sau đó số dư/lịch sử A, B không đổi.
- HTTP 5xx được xem là FAIL (từ chối không đúng tầng HTTP mong đợi), dù script vẫn dừng để tránh tiếp tục.
- Nếu API trả 2xx, script báo FAIL và dừng. Đối chiếu số dư/lịch sử ngay; không chạy lại ngay.
- Đây là kiểm thử cụ thể cho endpoint chuyển tiền, không thay thế việc xem xét toàn bộ controller/API.
