# Finora Flask Gateway unit tests — v9

Extends the 38-test v8 suite to 42 tests with four reverse-proxy behavior checks:

- Forwarding a query string without changing it.
- Forwarding the Authorization header to the backend.
- Forwarding a JSON request body, Content-Type, and Idempotency-Key.
- Not automatically following backend redirects.

## Run

Place `test_security_middleware.py` beside your local `app.py`, then run:

```powershell
python -m unittest -v test_security_middleware
```

All Redis and backend calls are mocked. These tests do not contact the real backend, Redis server, or database and do not create any financial transaction. The suite imports the local `app.py`, so run it against the version you intend to validate.

This package was syntax-checked and inspected for 42 test methods; it has not been executed against the user's local environment during packaging.
