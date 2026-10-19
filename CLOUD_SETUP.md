# REASON cloud foundation — release 0.2

Project: `reason-512120` • Region: `us-central1` • Owner: `tripodi@directlinemedical.app`

## What this release does

- Deployable owner-authenticated PWA shell and FastAPI API.
- Backend verifies Google Firebase ID tokens with revocation checks, exact verified owner email, Google sign-in provider and optional owner UID pin.
- Firestore stores account snapshots, packet exports, no-change card drafts and sanitized connection errors. Browser database access is denied by deployed Security Rules; the API uses its service account.
- Optional Alpaca **paper-only, read-only** import of account, positions and open orders. Only three allowlisted GET endpoints exist. Account ID is checked, redirects are refused, and neither live broker endpoints nor order-write methods exist.
- A packet export contains the versioned REASON mandate, schema, broker snapshot and missing evidence. No fictitious quotes or benchmark values are shown.
- No paid AI calls, trading worker, automatic trading or scheduled market analysis. Cards are visibly drafts, never activated. Trade decisions are rejected in this release because there is no live evidence feed or execution worker. No-change drafts can be saved and deduplicated.

This is a deliberate implementation stage, not a change to the agreed final behavior: the finished worker will automatically execute valid cards. Existing terminal trading remains untouched.

## Already completed by the owner

Billing linked; core service APIs enabled; default Firestore Native database created in us-central1; `reason-api` service account created with `roles/datastore.user`; Google identity provider and OAuth web client configured. Confirm the provider actually saves the values from Google's own copy buttons if sign-in later reports invalid_client. No OAuth client secret belongs in this repository or Cloud Run browser configuration.

## Deploy after the foundation PR is merged

Cloud Shell must have access to the private GitHub repository. If it doesn't, use `gh auth login --hostname github.com --git-protocol https --web` and complete GitHub's device approval outside chat. Do not paste a token or password here.

```bash
gh repo clone mtripodi31-gif/REASON-pwa
cd REASON-pwa
bash deploy/cloud-foundation.sh
```

If the repository is already cloned, use its existing directory and pull the merged branch rather than cloning over it. The script is hardcoded to REASON, not Direct Line.

The script:

1. Enables Firebase Management and Security Rules APIs alongside core services.
2. Verifies the pre-created database and API identity.
3. Adds Firebase to the existing Cloud project if needed, registers/reuses `REASON Web`, and reads its web SDK configuration.
4. Writes `deploy/runtime.env.yaml` locally (ignored by Git, build uploads and Docker). Firebase browser API keys are public configuration, not OAuth client secrets.
5. Preserves existing authorized domains and adds REASON's domains. Deploys deny-all browser Firestore rules to this dedicated project's default database. Does not disable the server API's IAM access.
6. Adds Firebase Authentication Viewer permission to the API identity for revocation checks and uses a separate `reason-build` identity with Cloud Run Builder permissions.
7. Builds/deploys `reason-api` from the root Dockerfile, request-billed, minimum zero, maximum two instances. No VM/trading worker starts.
8. Adds the returned Cloud Run hostname to the authorized-domain list and checks the public `/healthz` endpoint.

The static app shell, `/health` and Firebase public configuration are public. Every private account route requires the verified owner identity; making the Cloud Run service invokable does not make account data public. The script uses Google's supported `--no-invoker-iam-check` public-service configuration, which does not grant `allUsers` an IAM role and works with domain-restricted sharing. REASON still verifies the owner's Google token on every private API. If an organization explicitly enforces the Cloud Run Invoker IAM check, stop and design an IAP/hosting route rather than changing that organization policy.

The script preserves `REASON_OWNER_UID` and `REASON_ACCOUNT_ID` from an existing local `runtime.env.yaml`. If those values were changed only in the Cloud console, copy those nonsecret settings into that file before rerunning so the deployment does not clear them. Secret bindings should be reviewed on subsequent deployments. Deployment, IAM grants and billing were not performed by the PR itself.

The first deployment has a Cloud Run URL. Sign in there using the owner Google account, then confirm all other accounts are refused. `/api/me` returns the authenticated UID; you can pin it later using REASON_OWNER_UID. We have not yet verified the real Google sign-in flow or cloud permissions from this development environment.

## Connect Alpaca after sign-in is verified

```bash
bash deploy/connect-paper.sh
```

It asks for the PAPER key and secret using hidden terminal prompts, stores them in dedicated Google Secret Manager secrets, grants the API identity access to those two secrets only, and sets the expected paper account ID. It adds no broker order capability. Do not enter live credentials.

In the app, tap **Refresh paper account**. Confirm the account ID and all imported holdings/orders match Alpaca. Cash can be negative if the pre-existing account has borrowed; the app reports actual state without pretending to resolve it. Buying power is a broker figure, not authorization for REASON to borrow.

A snapshot consists of separate broker GETs, not an atomic broker transaction. If equity/cash/buying power changed during retrieval, packet generation stops and asks for another refresh. It still cannot guarantee executable freshness. The future trading worker must reconcile again before order submission.

There is no synthetic order history or benchmark curve on this cloud page. Last snapshot time is visible. Refresh is manual; no paid analysis is invoked by opening the page.

## Custom domain and iPhone

`reason.directlinemedical.app` is authorized for authentication but has **not** been routed or deployed by this PR. First verify Google login at the Cloud Run URL. Then configure the PWA's supported custom-domain hosting route and add only the required `reason` DNS record. Do not change the root or www Direct Line records. Firebase Hosting or a supported Cloud Run domain route can be selected at that step; costs and DNS authority need verification.

The cloud shell includes a PWA manifest and service worker. The service worker handles static shell assets only, not API requests or credentials. Browser session persistence is used for Google sign-in. iPhone Add to Home Screen, offline behavior and push notifications are not device-validated; push/email notifications remain unimplemented.

## Remaining before automated paper trading

Real market data with feed provenance; complete Trade Card execution contract; separated worker and durable order-intent/reconciliation state machine; cash reservations against actual fills; uncertain-order handling and partial fills; worker ownership/fencing and independent heartbeat alert; broker-native protective orders where supported; session/holiday handling; emergency controls; notifications; matched benchmark history. The existing terminal process must stop before the new worker submits orders to the same account.

Live mode and live credentials remain unsupported in this release. Trading cards cannot move from simulation/paper into live mode. The local simulator remains available through `run-preview.sh`, but is not used by the cloud API.

## Tests and CI

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-cloud.txt
.venv/bin/python -m pytest -q
.venv/bin/python tests/smoke_http.py
```

The workflow runs unit/API tests, HTTP smoke, JavaScript/shell checks and Docker image build. Local validation: 38 tests passed, smoke and syntax checks passed. Docker build runs in GitHub CI because Docker isn't installed in this local environment. Browser visual and real Google/Firestore/Alpaca integration tests remain pending deployment. No cloud bill or trade was generated by local tests.

## Official technical references

- Firebase ID token verification: https://firebase.google.com/docs/auth/admin/verify-id-tokens
- Firebase project/app management: https://firebase.google.com/docs/projects/api/workflow_set-up-and-manage-project
- Security Rules release API: https://firebase.google.com/docs/rules/manage-deploy
- Cloud Run source build identity: https://docs.cloud.google.com/run/docs/configuring/services/build-service-account
