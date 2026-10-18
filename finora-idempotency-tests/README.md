# Finora — kiểm thử idempotency và request đồng thời

Bộ test này hướng tới hai endpoint đang được frontend gọi:

- `POST /api/chuyen-khoan` với `Idempotency-Key`, body gồm `tkNguonId`, `tkDichId`, `soTien`, `moTa`.
- `POST /api/giao-dich` với `Idempotency-Key`, body gồm `tkId`, `danhMucId`, `loaiGd`, `soTien`, `ngayGd`, `moTa`.

**Mặc định chỉ đọc.** Khi bật test ghi, script gửi hai request đồng thời với cùng key/payload, mong hai response cùng trả về một ID; sau đó gửi lại cùng key nhưng khác payload, mong backend trả `409`.

## Lưu ý dữ liệu quan trọng

Chỉ dùng **tài khoản test riêng**. Nếu bật write test, script sẽ tạo tối đa:

- một bản ghi chuyển tiền `1.00 VND` từ tài khoản test nguồn sang tài khoản test đích;
- một bản ghi thu nhập `1.00 VND` trên tài khoản test đã chọn.

Các bản ghi được giữ trong database; script không có thao tác xóa. File `finora_idempotency_test_state.json` lưu key và payload trước khi gọi POST. Giữ nguyên file đó khi chạy lại, đặc biệt sau timeout/lỗi mạng, để những lần chạy tiếp dùng lại cùng key. Đừng commit file state hay mật khẩu lên Git.

## 1. Chuẩn bị

- Flask Gateway, C# API, Redis và MySQL đang chạy.
- Một tài khoản người dùng **chỉ dành cho test**.
- Ít nhất hai tài khoản tài chính test cùng đơn vị tiền tệ; tài khoản nguồn có số dư tối thiểu `1.00`.
- Ít nhất một danh mục thu nhập test.
- Python 3.10+; script dùng thư viện chuẩn, không cần `pip install`.

## 2. Đặt biến môi trường (PowerShell)

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "email-test-cua-ban@example.com"
$env:FINORA_PASSWORD = "mat-khau-tai-khoan-test"
```

Không ghi password trong script hoặc commit vào Git.

## 3. Chạy an toàn trước — chỉ đọc

```powershell
python .\test_finora_idempotency.py
```

Script đăng nhập, tải danh sách tài khoản/danh mục, hiển thị ID và **không gửi POST**.

## 4. Chạy test ghi khi đã chuẩn bị tài khoản riêng

```powershell
$env:FINORA_ALLOW_WRITE_TESTS = "YES"
python .\test_finora_idempotency.py --run-write-tests
```

Script sẽ hỏi ID tài khoản nguồn, tài khoản đích, tài khoản ghi khoản thu và danh mục thu nhập. Đọc kỹ cảnh báo rồi chỉ gõ `RUN ON TEST DATA` khi chắc chắn đã chọn đúng dữ liệu test.

## 5. Đọc kết quả

- `PASS` cho cùng key: hai request đồng thời cùng một yêu cầu trả về cùng ID.
- `PASS` cho payload khác: dùng lại key với nội dung khác bị từ chối bằng `409`.
- `FAIL` ở concurrent same-key: giữ nguyên file `finora_idempotency_test_state.json`; kiểm tra log C# và DB trước khi thử lại.
- `FAIL` khi payload khác không trả `409`: dừng test và kiểm tra DB ngay; backend có thể không enforce request hash như mong đợi.
- `BLOCKED`: điều kiện cấu hình/đăng nhập/dữ liệu chưa đáp ứng; script chưa chạy tiếp phần ghi hoặc đã chủ động dừng.

Muốn chạy một vòng test hoàn toàn mới thì cần hiểu rằng nó sẽ tạo thêm một chuyển tiền và một khoản thu mới. Chỉ sau khi kiểm tra và xác nhận các request trước đã hoàn tất, hãy lưu trữ/xóa file state và chạy lại khi thực sự cần.
