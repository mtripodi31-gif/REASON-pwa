# REASON paper execution — release 0.3

Project: `reason-512120` • Region: `us-central1` • Owner: `tripodi@directlinemedical.app`

## What this release does

- Keeps owner-only Google sign-in, server-only Firestore access and the dedicated Alpaca PAPER account binding.
- Adds Alpaca IEX stock snapshots to exported market-call packets, labeled as a single-exchange feed. Missing news, social search, consolidated indicators and benchmark history remain explicit.
- Validates and automatically activates complete `reason.trade-card.v1` cards. Cards are paper-only, regular-session, long-only, whole-share and cash-only. Long inverse/leveraged ETFs are supported. Existing shorts can be closed to zero but cannot be enlarged or flipped long in one card.
- Runs one persistent e2-small Compute Engine worker independently of the phone. It uses a Firestore lease, 10-second loop, deterministic Alpaca client order IDs and durable order intents.
- Submits new/increased long exposure as paper bracket limit orders with broker-resident stop and take-profit legs. A network timeout becomes `UNKNOWN`; the worker reconciles by client ID and pauses new entries instead of sending a fresh order.
- Adds Pause entries, Resume and confirmation-protected Close all. Pause allows risk-reducing orders. Close all cancels only REASON-owned orders and closes inherited long and short paper positions; it never silently cancels manual orders.
- Records recent REASON fills, worker events, sanitized errors and order uncertainty for copyable diagnostics.
- Makes no scheduled or automatic paid AI calls. **Ask AI remains disconnected and costs nothing.**

Live-money endpoints, live credentials, options and crypto are absent. The API cannot submit an order itself; only the worker identity can read the paper secrets and run the execution module.

## Deploy from Cloud Shell

After the PR is merged:

```bash
cd ~/REASON-pwa
git pull --ff-only origin main
bash deploy/paper-execution.sh
```

If the local account binding is missing, first run:

```bash
bash deploy/connect-paper.sh
```

The execution script asks you to type `STOPPED` after confirming the old Mac REASON process cannot restart. Two programs controlling the same paper account would make order attribution and reconciliation unreliable.

The script builds one versioned image, updates the request-billed Cloud Run API, creates a least-privilege `reason-worker` identity, and creates or updates `reason-worker-1`, an e2-small Container-Optimized OS VM. The worker VM uses an ephemeral external address for outbound Alpaca/Google access and no REASON-created inbound firewall rule. Expected baseline remains roughly $20–30/month before optional paid data or owner-triggered AI.

## First controlled lifecycle

After deployment, open the PWA and verify **Worker running**. Refresh the account and copy a fresh packet. For the first executable test, use a small paper target in one liquid symbol with a valid stop and take-profit. Paste the JSON and tap **Validate & activate paper card**. Confirm in REASON and Alpaca that exactly one deterministic `reason-...` order exists and that its bracket legs appear. Then test Pause and confirm it blocks new exposure without canceling broker-held exits.

Do not use buying power as the budget. Validation counts retained long holdings, pending limit buys and targets against equity. Inherited shorts should be transitioned to zero explicitly; REASON does not treat their proceeds as free long-only cash.

## Current boundaries

- IEX is one exchange rather than the consolidated market. REST snapshots are polled; streaming data, completed-bar indicators, RSI/VWAP, news/social sources, benchmark curves and push notifications remain future work.
- Executable cards are regular-session only. Orders may remain unfilled; target weights are instructions, not guaranteed fills.
- New/increased positions get bracket exits. Imported holdings remain inherited unless a later card changes them. Release 0.3 never invents exits for imported holdings.
- Partial/final fills are reconciled from recent broker orders. Advanced cancel/replace and consolidated exit migration for retained imported quantities remain limited and need forward paper testing.
- Firestore leasing plus deterministic client IDs reduce duplicate risk; they cannot create mathematical exactly-once delivery across a broker boundary.
- The worker VM is a single point of interruption. Broker-resident bracket legs continue at Alpaca, but unsubmitted conditional entries depend on the worker.

## Recovery and diagnostics

If the dashboard says **WORKER STOPPED / STALE**, copy diagnostics and inspect:

```bash
gcloud compute instances get-serial-port-output reason-worker-1 \
  --project=reason-512120 \
  --zone=us-central1-a \
  --port=1 | tail -n 120
```

Restart only the worker VM:

```bash
gcloud compute instances reset reason-worker-1 \
  --project=reason-512120 \
  --zone=us-central1-a
```

An `ORDER UNCERTAIN` error automatically pauses new entries. Check Alpaca using the displayed client order ID before resuming. Never create a replacement manually until the original ID is reconciled.

## Verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-cloud.txt
.venv/bin/python -m pytest -q
.venv/bin/python tests/smoke_http.py
node --input-type=module --check < cloud-web/cloud.js
bash -n deploy/cloud-foundation.sh deploy/connect-paper.sh deploy/paper-execution.sh
```

Local tests use injected identity, storage, market and broker fakes. They never touch Alpaca, Google Cloud or Direct Line. Real paper-order behavior must be verified with the controlled lifecycle after deployment.
