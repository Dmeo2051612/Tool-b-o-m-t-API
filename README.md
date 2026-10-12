# Flask Security Middleware

Project học tập về middleware bảo mật cho API, xây dựng bằng Flask, Redis và Werkzeug. Dự án minh họa cách kiểm soát request trước khi chuyển tiếp đến backend, đồng thời giúp tìm hiểu giới hạn của các biện pháp bảo vệ ở tầng ứng dụng.

> **Lưu ý:** Đây là project học tập và kiểm thử, chưa phải API Gateway hoàn chỉnh hoặc giải pháp bảo mật có thể tự thân bảo vệ hệ thống tài chính trong môi trường production.

## Tính năng

- **ProxyFix:** Hỗ trợ đọc IP và giao thức từ header chuyển tiếp khi cấu hình đúng số lượng proxy đáng tin cậy.
- **Rate Limiting:** Mặc định cho phép tối đa 5 request trong cửa sổ 10 giây theo IP client.
- **Bộ đếm nguyên tử trong Redis:** Lua script kết hợp tăng bộ đếm và thiết lập TTL để giảm nguy cơ sai lệch khi nhiều request đến đồng thời.
- **IP Blacklist:** Từ chối request có IP nằm trong Redis Set `blacklist_ips`. Giá trị được lưu trong Set là SHA-256 của IP.
- **CORS:** Chỉ cho phép các origin được cấu hình truy cập tài nguyên `/api/`.
- **API Reverse Proxy:** Chuyển tiếp request `/api/...` đến backend được cấu hình bằng `BACKEND_URL`.
- **Security Headers:** Thêm `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy` và `Cache-Control`. Header HSTS chỉ được thêm khi request được nhận diện là HTTPS.
- **Health Check:** Endpoint `/healthz` kiểm tra trạng thái kết nối Redis.
- **Fail-Closed:** Khi Redis gặp lỗi trong quá trình kiểm tra bảo vệ API, request nhận HTTP `503 Service Unavailable`.

## Công nghệ

- Python 3.10+
- Flask 3.1.3
- Flask-Cors 6.0.5
- Werkzeug 3.1.9
- redis-py 8.1.0
- Requests
- Redis Server

## Cấu trúc dự án

```text
project/
├── app.py
├── requirements.txt
└── README.md
```

Nếu file Python hiện tại có tên khác, hãy thay `app.py` trong các lệnh chạy bằng tên module tương ứng.

## Cài đặt trên Windows

### 1. Tạo môi trường Python

Mở PowerShell tại thư mục dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu PowerShell không cho phép kích hoạt môi trường ảo, có thể gọi trực tiếp `.\.venv\Scripts\python.exe` thay vì thay đổi chính sách thực thi trên toàn máy.

### 2. Khởi động Redis

Ứng dụng mặc định kết nối Redis tại `localhost:6379`, database `0`.

Nếu đã cài Redis Server, hãy khởi động dịch vụ và kiểm tra kết nối:

```powershell
redis-cli ping
```

Kết quả mong đợi:

```text
PONG
```

Hoặc nếu đã cài Docker Desktop, có thể chạy Redis bằng container:

```powershell
docker run --name flask-security-redis -p 127.0.0.1:6379:6379 -d redis:8
docker exec flask-security-redis redis-cli ping
```

Nếu container `flask-security-redis` đã tồn tại, dùng:

```powershell
docker start flask-security-redis
docker exec flask-security-redis redis-cli ping
```

Docker là một cách chạy Redis, không phải yêu cầu bắt buộc nếu máy đã có Redis Server đang hoạt động.

### 3. Cấu hình biến môi trường

Các biến dưới đây chỉ có hiệu lực trong cửa sổ PowerShell hiện tại:

```powershell
$env:REDIS_URL = "redis://localhost:6379/0"
$env:BACKEND_URL = "http://127.0.0.1:5001"
$env:ALLOWED_ORIGINS = "http://localhost:8080"
$env:MAX_REQUESTS = "5"
$env:TIME_WINDOW = "10"
$env:TRUSTED_X_FOR_COUNT = "0"
$env:TRUSTED_X_PROTO_COUNT = "0"
$env:PORT = "8081"
```

Ý nghĩa:

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `REDIS_URL` | Địa chỉ kết nối Redis | `redis://localhost:6379/0` |
| `BACKEND_URL` | Địa chỉ gốc của backend nhận request được chuyển tiếp | `http://127.0.0.1:5001` |
| `ALLOWED_ORIGINS` | Danh sách origin được CORS cho phép, phân tách bằng dấu phẩy | `http://localhost:8080` |
| `MAX_REQUESTS` | Số request tối đa trong một cửa sổ | `5` |
| `TIME_WINDOW` | Độ dài cửa sổ rate limit, tính bằng giây | `10` |
| `TRUSTED_X_FOR_COUNT` | Số proxy đáng tin cậy dùng để xử lý `X-Forwarded-For` | `0` |
| `TRUSTED_X_PROTO_COUNT` | Số proxy đáng tin cậy dùng để xử lý `X-Forwarded-Proto` | `0` |
| `PORT` | Cổng chạy Flask | `8081` |

`ALLOWED_ORIGINS` có thể nhận nhiều origin, ví dụ:

```powershell
$env:ALLOWED_ORIGINS = "http://localhost:8080,https://example.com"
```

Chỉ khai báo những origin thực sự được tin cậy. Origin bao gồm scheme, hostname và cổng nếu có; không thêm đường dẫn như `/api`.

`BACKEND_URL` phải là địa chỉ gốc hợp lệ của backend, không chứa đường dẫn, query string hoặc fragment. Backend phải đang chạy và có endpoint tương ứng nếu muốn kiểm thử việc chuyển tiếp request.

Ở môi trường local không có reverse proxy, giữ hai biến `TRUSTED_X_*_COUNT` bằng `0`. Chỉ tăng giá trị khi triển khai sau proxy đáng tin cậy đã được cấu hình để chuẩn hóa header chuyển tiếp. Không tin tưởng header do client tùy ý gửi.

Không commit mật khẩu Redis, token hoặc thông tin bí mật vào Git. Nếu Redis yêu cầu xác thực, cấu hình thông tin kết nối qua `REDIS_URL` của môi trường triển khai.

### 4. Chạy ứng dụng

Đảm bảo Redis đang chạy, sau đó thực hiện:

```powershell
python app.py
```

Theo cấu hình mặc định, Flask lắng nghe tại:

```text
http://127.0.0.1:8081
```

Ứng dụng hiện bind vào `127.0.0.1`, phù hợp cho kiểm thử trên máy local.

## Kiểm thử API

### 1. Kiểm tra sức khỏe

```powershell
curl.exe -i http://127.0.0.1:8081/healthz
```

Khi Redis kết nối thành công, endpoint trả HTTP `200` với JSON tương tự:

```json
{
  "status": "ok",
  "redis": "connected"
}
```

Nếu Redis không khả dụng, endpoint trả HTTP `503` và trạng thái `degraded`.

### 2. Gửi request đến API proxy

```powershell
curl.exe -i http://127.0.0.1:8081/api/data
```

Request sẽ được kiểm tra qua middleware, sau đó chuyển tiếp đến:

```text
http://127.0.0.1:5001/api/data
```

Backend tại `BACKEND_URL` cần đang chạy và cung cấp endpoint tương ứng. Nếu không kết nối được backend, proxy trả HTTP `502`; nếu backend hết thời gian phản hồi, proxy trả HTTP `504`.

### 3. Kiểm tra Rate Limiting

Mặc định, mỗi IP được phép tối đa 5 request trong cửa sổ 10 giây. Có thể gửi 6 request liên tiếp:

```powershell
1..6 | ForEach-Object {
    curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8081/api/data
}
```

Khi vượt giới hạn, middleware trả HTTP `429 Too Many Requests` và header `Retry-After`. Các request vẫn cần đi qua bước kiểm tra Redis trước khi được chuyển tiếp.

Kết quả kiểm thử còn phụ thuộc backend đang chạy và trạng thái bộ đếm hiện có. Chờ hết cửa sổ TTL hoặc xóa key kiểm thử phù hợp trước khi chạy lại.

### 4. Thêm IP vào blacklist

Code lưu SHA-256 của IP trong Redis Set `blacklist_ips`, vì vậy không thể thêm IP dạng rõ trực tiếp bằng `SADD blacklist_ips 127.0.0.1`.

Có thể tạo giá trị hash bằng Python:

```powershell
python -c "import hashlib; print(hashlib.sha256(b'127.0.0.1').hexdigest())"
```

Dùng chuỗi hash trả về ở lệnh sau:

```powershell
redis-cli SADD blacklist_ips "<SHA256_HASH>"
```

Gỡ IP khỏi blacklist bằng chính chuỗi hash đó:

```powershell
redis-cli SREM blacklist_ips "<SHA256_HASH>"
```

Nếu Redis chạy trong Docker, có thể dùng `docker exec flask-security-redis redis-cli ...` thay cho `redis-cli` trực tiếp trên máy.

> Chỉ đưa IP của môi trường kiểm thử vào blacklist. Khi kiểm thử local, nhiều request có thể cùng xuất phát từ `127.0.0.1`.

## Mã trạng thái đáng chú ý

| HTTP | Ý nghĩa |
|---|---|
| `200` | Health check thành công hoặc backend trả về thành công |
| `204` | Request `OPTIONS` được middleware trả lời |
| `400` | Không xác định được IP client hoặc query string không hợp lệ |
| `403` | IP nằm trong blacklist |
| `429` | Vượt giới hạn request |
| `502` | Không thể kết nối backend |
| `503` | Redis không khả dụng khi thực hiện kiểm tra bảo vệ, hoặc health check báo trạng thái degraded |
| `504` | Backend phản hồi quá thời gian cho phép |

Mã HTTP cuối cùng của request được chuyển tiếp có thể là mã do backend trả về.

## Giới hạn và lưu ý bảo mật

- Đây là project học tập, không phải API Gateway hoàn chỉnh đã được kiểm định bảo mật.
- Rate Limiting hiện dựa trên IP, không dựa trên tài khoản, API key hoặc danh tính người dùng.
- SHA-256 được dùng để tạo Redis key và nhận diện IP trong blacklist; điều này không tự động bảo đảm dữ liệu đã ẩn danh hoặc đáp ứng GDPR.
- CORS là chính sách của trình duyệt, không phải cơ chế xác thực client và không ngăn được mọi request trực tiếp đến API.
- Code hiện tại chưa triển khai Authentication/Authorization, JWT hoặc phân quyền người dùng.
- Code hiện tại chưa có kiểm tra Origin/Referer cho request thay đổi trạng thái; không nên xem CORS là biện pháp thay thế CSRF.
- Rate Limiting theo IP không ngăn được mọi hình thức DoS/DDoS và không thay thế các biện pháp bảo vệ ở tầng hạ tầng.
- Redis là thành phần phụ thuộc tập trung. Khi Redis lỗi, các request API bị từ chối theo chính sách fail-closed.
- `ProxyFix` chỉ an toàn khi số lượng proxy tin cậy được cấu hình chính xác và ứng dụng không thể bị truy cập theo cách cho phép client giả mạo header chuyển tiếp.
- `python app.py` sử dụng server phát triển của Flask; không dùng cách chạy này cho production.
- Khi triển khai thật, cần WSGI server phù hợp, HTTPS, cấu hình proxy chính xác, quản lý secret, giám sát, giới hạn tài nguyên và kiểm thử bảo mật độc lập.

Với ứng dụng quản lý chi tiêu, nên đặt nghiệp vụ giao dịch, xác thực, phân quyền và tính nhất quán dữ liệu trong backend chính (ví dụ Spring Boot + SQL Server). Chỉ bổ sung Flask làm gateway khi có yêu cầu định tuyến và vận hành rõ ràng.

## Hướng phát triển

- Bổ sung kiểm thử tự động cho rate limit, blacklist, timeout và lỗi Redis.
- Thêm logging và metrics để quan sát số request bị giới hạn hoặc từ chối.
- Đánh giá chính sách timeout, giới hạn kích thước request và xử lý header khi proxy.
- Chỉ triển khai Authentication/Authorization hoặc kiểm tra CSRF khi có yêu cầu và thiết kế phù hợp với backend.

## License

Chưa khai báo license. Nếu công khai repository, hãy thêm file `LICENSE` nếu muốn xác định rõ quyền sử dụng và phân phối mã nguồn.
