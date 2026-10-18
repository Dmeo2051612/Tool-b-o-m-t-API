# Finora — kiểm thử cách ly dữ liệu người dùng (v3)

Bộ kiểm thử đăng nhập hai tài khoản và chỉ gọi các endpoint GET sau khi đăng nhập. Nó không tạo, cập nhật, chuyển hoặc xóa dữ liệu tài chính.

## Điểm cải tiến

Bản trước yêu cầu cả hai người dùng phải có dữ liệu trên mỗi endpoint nên đánh dấu `SKIP` khi một bên rỗng. Bản này so sánh ngay khi ít nhất một người dùng có dữ liệu:

- Nếu ID xuất hiện trong kết quả của cả A và B: `FAIL`.
- Nếu cả hai có dữ liệu và ID không giao nhau: `PASS` (kiểm tra hai chiều).
- Nếu một bên có dữ liệu và bên kia rỗng, đồng thời ID không giao nhau: `PASS` có ghi rõ chỉ kiểm tra được một chiều.
- Nếu cả hai bên đều rỗng: `SKIP`; endpoint không có dữ liệu để kiểm tra.
- Nếu cả hai người dùng không có tài khoản tài chính: `BLOCKED`.

Cách so sánh này giả định các endpoint được kiểm tra trả về dữ liệu thuộc từng người dùng, không phải danh mục dùng chung toàn hệ thống. Nếu thiết kế của bạn cố ý chia sẻ bản ghi danh mục mặc định giữa người dùng, cần điều chỉnh quy tắc cho endpoint danh mục.

## Cài đặt và chạy (Windows PowerShell)

Cần Python 3.10+ và package `requests`:

```powershell
python -m pip install requests
$env:FINORA_BASE_URL = "http://127.0.0.1:8081"
$env:FINORA_EMAIL = "demo3@example.com"
$env:FINORA_PASSWORD = "mat-khau-user-A"
$env:FINORA_SECOND_EMAIL = "demo4@example.com"
$env:FINORA_SECOND_PASSWORD = "mat-khau-user-B"
python .\test_finora_user_isolation.py
```

Thay mật khẩu ví dụ bằng mật khẩu của hai tài khoản test. Không ghi mật khẩu vào file hoặc commit chúng lên Git.

## Diễn giải

`PASS` không chứng minh toàn bộ hệ thống an toàn; nó chỉ xác nhận việc so sánh các ID trả về tại lần chạy đó. Nếu muốn kiểm tra cả hai chiều cho mỗi endpoint, hãy tạo dữ liệu test riêng cho cả A và B. Dùng giao diện test, không nên dùng tài khoản tài chính thật.
