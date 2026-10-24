# Finora Flask Gateway unit tests v6

Version 6 adds three tests for `normalize_origin`:

- case-insensitive normalization of scheme and hostname;
- removal of default HTTP/HTTPS ports;
- rejection of user information, query strings, fragments, and invalid ports.

The suite contains 31 tests. Redis and the backend are mocked by the test suite, so it does not issue requests to the real backend or modify the database.

## Install / run

Copy `test_security_middleware.py` into the folder containing the real `app.py` (for this setup: `D:\UTE\GIT\Tool sec`) and run:

```powershell
python -m unittest -v test_security_middleware
```

Run from the folder containing `app.py`, because the test module imports `app`.

Note: the three new tests call `gateway.normalize_origin()` directly; they verify helper normalization behavior, not deployment behavior behind a production reverse proxy.
