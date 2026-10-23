# Finora Flask Gateway — automated middleware tests

These tests cover the existing Flask gateway middleware using Flask's test client. Redis and the upstream backend are mocked; tests do **not** send traffic to the real gateway, call the C# API, or change MySQL data.

## Where to put the test

Copy/overwrite `test_security_middleware.py` into the same folder as the gateway's `app.py` (for example, `D:\UTE\GIT\Tool sec`). This v2 test suite adds explicit assertions for middleware order. Do not copy it into the Finora application repository unless you specifically want to version-control gateway tests there.

## Run

Open PowerShell in that folder and run:

```powershell
python -m unittest -v test_security_middleware
```

The Python environment must already have the same runtime dependencies as `app.py` (`Flask`, `Flask-Cors`, `redis`, `requests`, and `Werkzeug`). No additional testing package is needed; this suite uses Python's built-in `unittest`.

## What is covered

- CORS preflight for allowed and disallowed origins
- CORS rejection of unapproved headers
- independent Origin and Referer validation
- malformed Origin / Referer values
- allowed sources continue to backend authentication; missing source headers are not blocked by this middleware
- Redis IP blacklist
- Rate Limit response including `Retry-After`
- Explicit order checks: Rate Limiting executes before CORS preflight and before Origin/Referer validation
- fail-closed behavior when Redis raises an error
- security headers on rejection responses
- `/healthz` response

## Notes

These are isolated unit tests, not a replacement for the manual integration checks already performed against the running gateway. They mock the Redis and upstream HTTP calls to avoid changing live state.
