# Finora — kiểm tra cách ly giao dịch B → A (v4)

Công cụ bổ sung cho `finora-user-isolation-tests-v3`. Mục tiêu là tạo một marker giao dịch **thuộc riêng người dùng B**, sau đó kiểm tra marker có xuất hiện đúng một lần trong GET lịch sử của B và không xuất hiện trong GET lịch sử của A.

## An toàn mặc định

- Mặc định chỉ đăng nhập và gọi GET để liệt kê tài khoản/danh mục của B.
- Không có POST ghi tài chính, trừ khi đồng thời truyền `--create-marker`, đặt `FINORA_ALLOW_ISOLATION_WRITE=YES` và gõ đúng câu xác nhận.
- Chế độ ghi sẽ tạo một khoản thu 1.00 VND trên tài khoản TEST của B. Bản ghi không tự bị xóa.
- Khóa idempotency + payload được lưu trước lần POST trong `finora_user_b_isolation_state.json`. Giữ nguyên file để chạy lại an toàn; không xóa khi chưa điều tra yêu cầu trước.
- Script không ghi mật khẩu vào file và dùng Python standard library, không cần `requests`.

## 1. Cấu hình PowerShell

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "demo3@example.com"
$env:FINORA_PASSWORD = "<mat-khau-user-A>"
$env:FINORA_SECOND_EMAIL = "demo4@example.com"
$securePasswordB = Read-Host "Nhap mat khau demo4" -AsSecureString
$env:FINORA_SECOND_PASSWORD = [System.Net.NetworkCredential]::new("", $securePasswordB).Password
```

Không gửi mật khẩu qua chat hoặc commit nó vào Git. Biến môi trường chỉ tồn tại trong cửa sổ PowerShell hiện tại.

## 2. Chạy chế độ chỉ đọc

```powershell
python .\test_finora_user_b_isolation_marker.py
```

Script hiển thị các tài khoản và danh mục của B. Nếu B chưa có tài khoản tài chính, kết quả cho biết cần tạo tài khoản TEST thuộc B trước; script không tự tạo tài khoản hoặc gọi POST.

## 3. Kiểm tra B → A (chỉ khi B đã có tài khoản TEST)

```powershell
$env:FINORA_ALLOW_ISOLATION_WRITE = "YES"
python .\test_finora_user_b_isolation_marker.py --create-marker
```

Chỉ chọn tài khoản TEST thuộc B và danh mục thu nhập TEST. Gõ chính xác `CREATE ONE 1 VND TEST INCOME FOR B` để xác nhận. Nếu B không có tài khoản hoặc danh mục thu nhập, script dừng trước khi ghi.

Sau khi ghi, script GET `/api/giao-dich` dưới cả hai tài khoản và đánh giá:

- `PASS`: marker xuất hiện đúng một lần trong lịch sử B, không xuất hiện trong A.
- `FAIL`: marker xuất hiện trong lịch sử A hoặc bị ghi nhiều lần ở B.
- `BLOCKED`: không thấy marker trong lịch sử B; API có thể giới hạn lịch sử, cần kiểm tra phản hồi hoặc database trước khi kết luận.

Script không tự xóa marker. Một `PASS` chỉ chứng minh đường dữ liệu thu/chi đang được kiểm tra tại thời điểm chạy; vẫn nên chạy bộ v3 cho các endpoint tài khoản, danh mục, chuyển tiền và ngân sách. Danh mục có thể được thiết kế là dùng chung, vì vậy không được kết luận rò rỉ chỉ dựa trên các ID danh mục trùng nếu thiết kế quy định danh mục mặc định dùng chung.
