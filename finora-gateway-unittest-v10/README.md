# Finora Flask Gateway unit tests — v10

This package extends the current `test_security_middleware.py` suite from 42 to 48 tests.

## Install
Copy `test_security_middleware.py` to the directory containing the project's `app.py`.

## Run
```powershell
python -m unittest -v test_security_middleware
```

## New coverage in v10
- Invalid Origin is rejected for PUT, PATCH, and DELETE.
- Allowed PUT, PATCH, and DELETE requests are forwarded using their original methods.
- GET with a disallowed Origin is still subject to backend authentication and does not receive CORS permission for that Origin.
- `/healthz` bypasses API-only blacklist and rate-limit checks.
- Non-API paths do not access Redis or the backend proxy.
- Backend status code and JSON response body are preserved by the proxy.

Redis and backend calls are mocked by the existing suite. These unit tests do not connect to the live Redis service, the C# API, or MySQL, and do not create financial transactions.
