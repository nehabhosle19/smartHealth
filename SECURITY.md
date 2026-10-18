# Security

## Reporting a vulnerability
Please do **not** open a public issue. Report privately via GitHub's
"Report a vulnerability" (Security tab) and include steps to reproduce.

## Design summary
| Area | Control |
|---|---|
| Passwords | PBKDF2-HMAC-SHA256, 600 000 iterations, per-user salt; 12+ chars with mixed case and a digit enforced by the CLI |
| Sessions | HMAC-signed, expiring tokens in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; changing a password or deactivating a user revokes outstanding tokens |
| CSRF | SameSite=Strict plus a required `X-Requested-With` header on cookie-authenticated writes |
| Authorisation | Role (admin/staff) and per-facility checks on every endpoint; staff can only read/write their own centre |
| Brute force | Failed-login throttling per username and per IP; constant-time password check even for unknown users |
| Input | Strict bounded Pydantic models (`extra=forbid`), 64 KB body limit, date-range checks, parameterised SQL via SQLAlchemy |
| Browser | CSP (`default-src 'self'`), HSTS, `nosniff`, no framing, no inline script/style, DOM built with `textContent` only |
| Config | Production refuses to start without a strong `SMARTHEALTH_SECRET` and `Secure` cookies; Host header validated via `SMARTHEALTH_ALLOWED_HOSTS` |
| Ops | No default accounts or passwords; demo data refused in production; audit log of logins and data writes (`smarthealth.audit`); non-root, read-only container |

## Known limitations / operator responsibilities
- **Terminate TLS in front of the app** (reverse proxy or platform load balancer). Cookies are `Secure`.
- Login throttling is **per process**. With several workers/instances an attacker gets N× the attempts;
  add rate limiting at the proxy (e.g. nginx `limit_req`) for stronger protection.
- Tokens are stateless: a stolen token stays valid until expiry (default 8 h) unless the password is changed.
- No MFA. Admin accounts should use long unique passwords.
- Health-centre data is operational, not patient-identifiable: the app stores no patient names or records.
  Doctor names are the only personal data. Do not extend it to patient records without a privacy review.
