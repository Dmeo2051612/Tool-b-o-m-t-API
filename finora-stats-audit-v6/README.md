# Finora — đối chiếu thống kê với lịch sử thu/chi v6 (chỉ đọc)

Công cụ này tiếp nối audit cách ly dữ liệu v5. Nó kiểm tra xem các tổng thống kê trả về cho từng tài khoản có khớp với lịch sử thu/chi và thống kê theo ngày trong cùng khoảng thời gian hay không.

## An toàn dữ liệu

- `POST` chỉ được dùng cho `/api/auth/login`.
- Các endpoint dữ liệu tài chính chỉ được gọi bằng `GET`.
- Không tạo, sửa, chuyển hoặc xóa giao dịch.
- Không lưu email/mật khẩu vào file; dùng biến môi trường PowerShell.

## Kiểm tra

Với từng người dùng A/B, script dùng khoảng từ ngày đầu tháng đến hôm nay và lấy:

- `GET /api/giao-dich`
- `GET /api/thong-ke/theo-ngay?tuNgay=...&denNgay=...`
- `GET /api/thong-ke/tong-quan?tuNgay=...&denNgay=...`

Sau đó đối chiếu:

1. `chenhLech` bằng `tongThu - tongChi`.
2. Tổng `tongThu`/`tongChi` từ thống kê theo ngày khớp với tổng quan.
3. Nếu số bản ghi lịch sử trong khoảng bằng `soGiaoDich` của tổng quan và ngày giao dịch hợp lệ, so sánh tổng thu/chi theo lịch sử với tổng quan.
4. Khi lịch sử đã được chứng minh đủ theo số lượng giao dịch, so sánh thu/chi từng ngày giữa lịch sử và thống kê theo ngày.

Nếu số giao dịch từ lịch sử khác với `soGiaoDich` tổng quan, script báo `BLOCKED` thay vì tự kết luận lỗi, vì endpoint lịch sử có thể giới hạn số dòng hoặc phân trang. Khi đó cần xác minh endpoint trả đủ bản ghi trước khi kết luận.

## Chạy trong PowerShell

Trong cùng cửa sổ PowerShell đã thiết lập các biến đăng nhập A/B ở bộ v5, chạy:

```powershell
python .\verify_finora_stats_against_transactions.py
```

Nếu là cửa sổ mới, đặt lại các biến (không lưu mật khẩu vào file):

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "demo3@example.com"
$a = Read-Host "Nhap mat khau demo3" -AsSecureString
$env:FINORA_PASSWORD = [System.Net.NetworkCredential]::new("", $a).Password
$env:FINORA_SECOND_EMAIL = "demo4@example.com"
$b = Read-Host "Nhap mat khau demo4" -AsSecureString
$env:FINORA_SECOND_PASSWORD = [System.Net.NetworkCredential]::new("", $b).Password
python .\verify_finora_stats_against_transactions.py
```

Cần Python 3.10+ và `requests`. Nếu chưa cài:

```powershell
python -m pip install requests
```

## Diễn giải

- `PASS`: phép đối chiếu tương ứng khớp.
- `FAIL`: dữ liệu đủ để đối chiếu nhưng tổng/chi tiết mâu thuẫn.
- `BLOCKED`: chưa có đủ dữ liệu được endpoint cung cấp để kết luận; không đồng nghĩa chắc chắn có lỗi.

Bài này là kiểm tra tích hợp trên dữ liệu API trả về, chưa thay thế việc review điều kiện lọc `userId` trong source C# hoặc kiểm tra phân trang/giới hạn ở repository/service.
