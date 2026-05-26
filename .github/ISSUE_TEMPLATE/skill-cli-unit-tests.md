---
name: "Tracking — skill-cli unit tests"
about: "Cover the stateful logic in skill_cli.py with pytest"
title: "skill-cli: add unit tests for token cache, refresh, and config resolution"
labels: ["tests", "phase-2"]
assignees: []
---

## Why

`skills/skill-cli/skill_cli.py` is a small but stateful program: it
caches tokens, judges expiry, refreshes silently, and resolves config
from two layered sources. None of that has unit tests.

Edge cases that should have explicit assertions:

1. **`creds_expired()` ISO time parsing** — handles `Z` suffix vs
   `+00:00` offset; rejects malformed strings as expired (fail-safe).
2. **`refresh_tokens()` fallback** — Cognito sometimes returns no new
   `refresh_token`; we keep the old one. Currently relies on a
   `if "refresh_token" not in tokens` check that's untested.
3. **OAuth callback state mismatch** — `_CallbackHandler` captures
   `state`; `login()` aborts on mismatch. No test ensures this rejection.
4. **PKCE verifier round-trip** — `_make_pkce_pair()` must produce a
   verifier whose SHA-256-then-base64url matches the challenge.
5. **TOML vs env var precedence** — env vars win when both are set;
   missing keys produce an error message that lists *all* missing keys
   at once (currently true; not pinned by a test).
6. **`whoami` claims decoding** — robust to id_token padding; rejects
   malformed JWT.

## Setup

Use `pytest` + `pytest-mock` + `unittest.mock`. Mock:
- `keyring.set_password` / `get_password` (no real keyring access)
- `requests.post` (Cognito token endpoint)
- `boto3.client("cognito-identity")` (Identity Pool calls)
- `webbrowser.open` (no browser launch in CI)

For OAuth callback tests, exercise `_CallbackHandler.do_GET`
directly with a fake `BaseHTTPRequestHandler` setup or a real
`http.server.HTTPServer` on port 0.

## Acceptance

- `pytest skills/skill-cli/tests/` passes locally
- Coverage on `skill_cli.py` ≥ 80%
- CI runs the test on every PR (GitHub Action — also tracked in
  `docs/06-future-optimizations.md` for general CI work)

## Out of scope

- End-to-end test against a real Cognito User Pool (would require an
  AWS account in CI; defer to later)
- Test the `cdk/lib/identity-stack.ts` (different language stack)
