# Verification — preview 0.1

October 16, 2026

- 24 backend tests passed with pytest.
- API tests verify access-code authentication, cross-origin rejection, destructive-action confirmation, no-store account responses, valid/invalid cards and duplicate submissions.
- Engine tests verify cash-only execution, reserved cash, stop/take exits, expiry, replacement, pause/resume, close-all, invalid evidence, stale account revisions, stale quotes, restart from persisted pending orders and duplicate prevention.
- JavaScript syntax checks passed for app.js and sw.js.
- A local HTTP smoke check is included in the delivered tests.
- One non-failing dependency warning: current Starlette TestClient deprecates httpx in favor of httpx2. Existing API tests pass.
- Full browser rendering and iPhone device validation are **not complete**. Browser installation was attempted, but the download returned an invalid archive. Responsive CSS and PWA metadata are implemented, but this is not a claim of device certification.
- No Google Cloud deployment, real brokerage calls, paid AI calls or modifications to Direct Line were performed.

These results apply to the local simulator. They do not validate future Alpaca order handling, partial fills, distributed workers, real-time data quality, production authorization, push delivery or live trading.

## Cloud foundation 0.2 — October 19, 2026

- 38 total local tests passed: the original 24 simulation/API checks plus 14 cloud-foundation checks.
- Cloud checks cover owner/provider/verified-email/UID restrictions, invalid sessions, public/private route separation, read-only snapshot persistence, missing credentials, sanitized broker failures, draft deduplication, mismatched packet/mode/timestamps, size limits, account-change detection and the fixed paper GET-only broker allowlist.
- HTTP smoke and JavaScript/shell syntax checks passed.
- Tests use injected identity verification, in-memory storage and broker stubs; they do not claim real OAuth, Firestore or broker integration validation. No real cloud services or keys were used.
- Docker isn't installed locally; the Docker build is included in GitHub CI. Cloud deployment scripts require owner execution in Cloud Shell. They were syntax-checked and official API shapes researched, not executed against the cloud project.

## Paper execution 0.3 — October 19, 2026

- 44 local tests passed, plus HTTP smoke and JavaScript/shell syntax checks.
- Worker checks cover stable feed-labeled evidence IDs, deterministic bracket identity, duplicate-intent suppression, pause behavior, inherited-short closure, expiry, close-all and protection of external/manual orders.
- API validation now accounts for evidence IDs, inherited shorts, required exits, pending-buy reservations and cash-only whole-portfolio targets.
- Submission timeouts are coded as uncertain and pause entries; they are never interpreted as a safe retry. Real timeouts, partial fills, bracket-leg events and VM restart recovery still require controlled Alpaca paper testing.
- No paper order, cloud resource or paid AI call was created during local verification.
