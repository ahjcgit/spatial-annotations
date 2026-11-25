# Login rate limit tests

`POST /auth/login` is throttled by an in-memory limiter in
[`backend/app/ratelimit.py`](../backend/app/ratelimit.py). Four tests in
[`backend/tests/test_api.py`](../backend/tests/test_api.py) cover it. They use no
network and never sleep, so they finish in about a second.

## Behaviour under test

| Limit | Default | Setting | Window |
| --- | --- | --- | --- |
| All login attempts per client IP | 20 | `LOGIN_ATTEMPTS_PER_IP_PER_MINUTE` | 60 s |
| Failed logins per client IP and username | 5 | `LOGIN_FAILURES_PER_ACCOUNT_PER_15_MINUTES` | 15 min |

The limiter is checked before any password hashing. A throttled request gets `429`
with a `Retry-After` header in whole seconds. A successful login clears the failure
count for that IP and username. Failures are keyed by IP and username together, so a
remote attacker cannot lock a user out from another network.

## Running

From the repository root:

```bash
(cd backend && ../.venv/bin/python -m pytest -v -k "throttled or clears_failures or sliding_window")
```

Run pytest from `backend/`; the tests import the application as `app.main`.

## Test setup

- The `client` fixture in `backend/tests/conftest.py` creates a fresh app with a
  temporary SQLite database. The limiter lives in `create_app`, so every test starts
  with empty counts.
- The `users` fixture registers and logs in `alice`, `bob`, and `carol` with password
  `correct-horse-test`. Those three logins count toward the per-IP limit.
- `TestClient` reports its client IP as `testclient`. Tests simulate a second IP with
  `TestClient(client.app, client=("203.0.113.9", 50000))`, using a documentation-only
  address.

## Tests

### `test_login_failures_throttled_per_ip_and_username`

1. Five wrong passwords for `alice` each return `401`.
2. A sixth attempt with the **correct** password returns `429`. A locked account does
   not reveal whether a guess was right.
3. `Retry-After` is between 1 and 900 seconds.
4. The submitted password does not appear in the response.
5. `bob` can still log in from the same IP: the lock covers only that username.
6. `alice` can still log in from another IP: other networks are unaffected.

### `test_login_success_clears_failures`

Four failures, one success, then four more failures. All later failures return `401`.
Without the reset, the fifth cumulative failure would trigger the lock and return `429`.

### `test_login_attempts_throttled_per_ip`

`monkeypatch` sets `LOGIN_ATTEMPTS_PER_IP_PER_MINUTE=3` before building a dedicated
app; the shared fixture is created too early for the setting to apply. Three
**successful** logins return `200` and the fourth returns `429`, showing the per-IP
limit counts every attempt. A request from another IP still succeeds.

### `test_sliding_window_expires`

Tests `SlidingWindow` directly with an injected clock (`clock=lambda: now[0]`), so
expiry is checked without waiting.

| Fake time | Action | Expected |
| --- | --- | --- |
| 0 s | Two `acquire` calls, limit 2 per 60 s | Both return `0` (allowed) |
| 0 s | Third `acquire` | `60` seconds to wait |
| 59.5 s | `acquire` | `1`; waits round up and are never `0` while blocked |
| 60 s | `acquire` | `0`; the earlier hits have expired |

It also creates a window with `max_keys=2` and records keys `a`, `b`, `c`. Only `b` and
`c` remain, confirming the oldest key is evicted so memory stays bounded.

## Not covered

- Real client IPs behind Caddy. The HTTPS Compose override sets `FORWARDED_ALLOW_IPS`
  so Uvicorn uses `X-Forwarded-For`; check this in a deployed environment.
- Multiple Uvicorn workers or replicas. Counts are per process and reset on restart.
- `POST /auth/register`, which is not rate limited.
- Concurrent requests. Parallel failures from one IP can briefly exceed the failure
  limit; the per-IP attempt limit still bounds them.
