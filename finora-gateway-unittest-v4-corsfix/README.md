# Finora Flask Gateway unit tests v4 — CORS assertion fix

This package contains the 25-test `test_security_middleware.py` suite.

## Fix in this version

The prior suite failed `test_hop_by_hop_and_cors_headers_from_backend_are_filtered` because it expected `Access-Control-Allow-Origin` to be absent from the entire Flask response. The proxy filters the upstream CORS header, but Flask-CORS can correctly add the configured allowlisted origin afterward. The test now sends the allowed Origin and asserts the final response contains `http://localhost:8080`, never the untrusted upstream origin `https://evil.example`.

## Run

Copy `test_security_middleware.py` beside `app.py`, then run from that directory:

```powershell
python -m unittest -v test_security_middleware
```

Redis and backend network calls are mocked by the tests. They do not create transactions or change the database. This environment does not include Flask, Flask-CORS, or redis-py, so the suite has not been executed here; run it in the user's Flask Gateway environment.
