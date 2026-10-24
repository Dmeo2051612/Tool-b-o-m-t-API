# Finora Flask Gateway unit tests — v8

Adds four tests to the v7 suite, for a total of 38 tests:

- A GET request with an untrusted Referer is not blocked by the write-method Origin/Referer guard; backend JWT auth still returns 401.
- Empty Origin is rejected for a state-changing request.
- Empty Referer is rejected for a state-changing request.
- HTTPS requests receive the configured HSTS header and the backend receives `X-Forwarded-Proto: https`.

## Run

Place `test_security_middleware.py` beside your local `app.py`, then run:

```powershell
python -m unittest -v test_security_middleware
```

All Redis and backend requests are mocked; the suite does not call the real API, Redis server, or database. It tests the current `app.py` by importing it, so use the latest version of `app.py` whose behavior you intend to validate.

The test suite has been syntax-checked and inspected for 38 test methods. This package was not run against the user's local API or source tree during creation.
