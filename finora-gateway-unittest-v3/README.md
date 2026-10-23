# Finora Flask Gateway - unit test v3

## Mục đích

Bộ này mở rộng bộ kiểm thử middleware trước đó từ 17 lên 19 bài. Hai bài mới kiểm tra Gateway ghi đè các header `X-Forwarded-For` và `X-Forwarded-Proto` do client tự gửi khi chạy cấu hình local không có reverse proxy tin cậy.

## Cài đặt

Giải nén ZIP. Sao chép `test_security_middleware.py` vào `D:\UTE\GIT\Tool sec\` (cùng thư mục với `app.py`):

```powershell
Copy-Item ".\finora-gateway-unittest-v3\test_security_middleware.py" "D:\UTE\GIT\Tool sec\test_security_middleware.py" -Force
cd "D:\UTE\GIT\Tool sec"
python -m unittest -v test_security_middleware
```

Nếu đã giải nén vào tên thư mục khác, thay đường dẫn nguồn trong `Copy-Item` bằng vị trí file thực tế.

## Hai kiểm thử được thêm

- `test_client_supplied_x_forwarded_for_is_overwritten`: client gửi IP giả, nhưng Gateway chuyển IP do request socket cung cấp cho backend.
- `test_client_supplied_x_forwarded_proto_is_overwritten`: client gửi `X-Forwarded-Proto: https` qua HTTP local, nhưng Gateway chuyển tiếp `http` và không thêm HSTS chỉ vì header giả.

Bộ test đặt `TRUSTED_X_FOR_COUNT=0` và `TRUSTED_X_PROTO_COUNT=0` trước khi import `app`, mô phỏng cấu hình local không có proxy tin cậy. Khi triển khai sau reverse proxy thật, hãy cấu hình số proxy tin cậy chính xác theo hạ tầng.

## An toàn

Tất cả Redis và backend được mock. Bộ test không gọi API thật, không kết nối Redis thật, không tạo giao dịch, không thay đổi database và không thay đổi code `app.py`.
