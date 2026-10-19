# REASON PWA

Private trading desk for REASON. Owner: `tripodi@directlinemedical.app`. Dedicated Google project: `reason-512120`.

## Cloud foundation 0.2

Google owner sign-in, Firestore state, packet export, draft cards and optional **read-only Alpaca paper account** import. No trading worker or paid AI calls. Trading is visibly disabled; no-change drafts are accepted, while new trade decisions require a later execution/data release.

Read [CLOUD_SETUP.md](CLOUD_SETUP.md) for deployment and current limits. After merging and authenticating GitHub CLI in Cloud Shell:

```bash
gh repo clone mtripodi31-gif/REASON-pwa
cd REASON-pwa
bash deploy/cloud-foundation.sh
```

Deployment is manual. CI tests changes but never deploys or trades. Broker keys belong only in Secret Manager through the optional `deploy/connect-paper.sh` hidden prompts. Do not commit credentials or upload medical data.

## Local simulation preview 0.1

Requires Python 3.12+:

```bash
bash run-preview.sh
```

Open the local URL printed by the launcher and use its preview access code. Click Load demo, then Validate & activate to exercise simulated entries, fills, retained exits, pause/resume and close-all. The fictional $100,000 account and prices are not market evidence. Ctrl+C stops this local worker; account state persists in the ignored data directory.

The local simulator is separate from the cloud implementation. It uses SQLite and a process-local loop; it cannot connect to Alpaca or run as Cloud Run's production API. Its asset set and immediate/above/below/stop/take rules are intentionally limited. Its successful tests do not establish production broker exactly-once execution, distributed worker safety, or investment returns.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-cloud.txt
.venv/bin/python -m pytest -q
.venv/bin/python tests/smoke_http.py
```

See [BUILD_SPECIFICATION.md](BUILD_SPECIFICATION.md) for the agreed final design and [TEST_REPORT.md](TEST_REPORT.md) for verification scope. The repository contains no live broker integration, secrets or automatic deployment workflow.
