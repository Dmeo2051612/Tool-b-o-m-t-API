# Finora Gateway hardening v11 — lọc Server/Date từ backend

Gói này thêm 1 unit test vào bộ v10 (48 → 49 tests) và hướng dẫn chỉnh đúng một vị trí trong `app.py`.

## 1. Sửa `app.py` trước khi chạy test

Mở `D:\UTE\GIT\Tool sec\app.py` và tìm `RESPONSE_EXCLUDED_HEADERS`. Trong set hiện tại có dạng:

```python
RESPONSE_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {
    "content-length",
    "content-encoding",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-allow-credentials",
    "access-control-expose-headers",
    "access-control-max-age"
}
```

Thêm đúng hai mục `"server"` và `"date"` vào set đó, ví dụ:

```python
RESPONSE_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {
    "content-length",
    "content-encoding",
    "server",
    "date",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-allow-credentials",
    "access-control-expose-headers",
    "access-control-max-age"
}
```

Chỉ sửa set này; không thay toàn bộ `app.py`. Sao lưu file trước khi sửa nếu cần.

Mục tiêu là không chuyển tiếp hai header `Server` và `Date` mà backend C# gửi lên. Flask/Werkzeug vẫn có thể tự tạo header `Server`/`Date` của Gateway ở tầng HTTP, nên thay đổi này loại bỏ bản header upstream bị trùng, **không** ẩn hoàn toàn banner Werkzeug của máy chủ phát triển.

## 2. Cài bộ test mới

Giải nén ZIP. Trong PowerShell:

```powershell
cd "D:\UTE\GIT\Tool sec"
Copy-Item ".\finora-gateway-hardening-v11\test_security_middleware.py" ".\test_security_middleware.py" -Force
python -m unittest -v test_security_middleware
```

Nếu bạn giải nén thư mục ở chỗ khác, hãy sửa đường dẫn nguồn `Copy-Item` cho đúng. Không ghi đè `app.py` bằng file trong ZIP vì gói này không chứa bản `app.py` hoàn chỉnh.

## 3. Kết quả kỳ vọng

- `49 tests` chạy thành công nếu các 48 test cũ vẫn pass và test mới pass.
- Test mới xác nhận `Server: Kestrel` và `Date` được backend trả về không bị sao chép vào response của Flask app test client, trong khi header không thuộc danh sách loại trừ vẫn được giữ.

Bộ test mock Redis và backend; nó không gửi request tới API/Redis thật. Sau khi unit test pass, kiểm tra lại `curl.exe -i http://127.0.0.1:8081/api/tai-khoan` để xác nhận phản hồi thực tế vẫn trả `401` không có JWT và không còn header Kestrel/Date upstream bị lặp. Các header do server phát triển Werkzeug tự thêm vẫn có thể xuất hiện.
