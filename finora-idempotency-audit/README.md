# Finora — audit idempotency (chỉ đọc)

Script này bổ sung bước kiểm tra **sau** khi chạy `test_finora_idempotency.py`. Nó không gửi POST ghi nghiệp vụ, không cập nhật hay xóa dữ liệu. Nó đăng nhập qua `/api/auth/login`, sau đó chỉ GET `/api/tai-khoan`, `/api/chuyen-khoan`, `/api/giao-dich`.

Nó đọc `finora_idempotency_test_state.json` được tạo bởi bộ test idempotency, rồi xác minh:

- Có đúng một bản ghi lịch sử chuyển tiền mang mô tả test đã lưu, với nguồn/đích/số tiền đúng payload.
- Có đúng một bản ghi lịch sử thu/chi mang mô tả test đã lưu, với tài khoản/danh mục/loại/số tiền đúng payload.
- In số dư hiện tại của các tài khoản liên quan; tùy chọn so sánh số dư với giá trị kỳ vọng bạn cung cấp.

## Cách chạy (PowerShell)

Đặt thông tin đăng nhập test như khi chạy bộ kiểm thử trước:

```powershell
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "demo3@example.com"
$env:FINORA_PASSWORD = "MAT_KHAU_TEST"
```

Chép `finora_idempotency_test_state.json` từ thư mục `finora-idempotency-tests` sang cùng thư mục với `verify_finora_idempotency.py`, rồi chạy:

```powershell
python .\verify_finora_idempotency.py
```

Theo kết quả bạn cung cấp trước kiểm thử, số dư ban đầu là tài khoản #4 = 56,000 VND và tài khoản #5 = 51,000 VND. Nếu chưa có giao dịch nào khác tác động hai tài khoản kể từ lúc đó, chuyển 1 VND từ #4 sang #5 và ghi thu 1 VND vào #4 sẽ cho số dư kỳ vọng #4 = 56,000 VND, #5 = 51,001 VND. Có thể kiểm tra thêm:

```powershell
python .\verify_finora_idempotency.py --check-balance 4=56000 --check-balance 5=51001
```

Chỉ dùng so sánh số dư khi chắc chắn không có giao dịch khác phát sinh sau lần ghi nhận số dư ban đầu. Nếu API lịch sử chỉ trả các bản ghi gần nhất và test record không có trong kết quả, script có thể báo không tìm thấy; hãy kiểm tra giới hạn endpoint/DB trước khi kết luận có lỗi.

**Bảo mật:** không gửi `finora_idempotency_test_state.json`, mật khẩu hoặc access token lên GitHub. Đảm bảo file state và bộ test nằm trong thư mục test riêng.
