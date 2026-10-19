#!/usr/bin/env bash
# Optional next phase: read-only connection. Values never become shell arguments or files.
set -euo pipefail
REASON_PROJECT='reason-512120'
REASON_API="reason-api@$REASON_PROJECT.iam.gserviceaccount.com"
for REASON_SECRET in alpaca-paper-key alpaca-paper-secret; do
  if ! gcloud secrets describe "$REASON_SECRET" --project="$REASON_PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$REASON_SECRET" --project="$REASON_PROJECT" --replication-policy=automatic
  fi
  read -r -s -p "Paste $REASON_SECRET (hidden): " REASON_VALUE
  printf '\n'
  if [ -z "$REASON_VALUE" ]; then printf 'Empty value; stopped.\n' >&2; exit 1; fi
  printf '%s' "$REASON_VALUE" | gcloud secrets versions add "$REASON_SECRET" --project="$REASON_PROJECT" --data-file=- >/dev/null
  unset REASON_VALUE
  gcloud secrets add-iam-policy-binding "$REASON_SECRET" --project="$REASON_PROJECT" --member="serviceAccount:$REASON_API" --role=roles/secretmanager.secretAccessor --condition=None --quiet >/dev/null
 done
read -r -p 'Alpaca PAPER account ID: ' REASON_ACCOUNT
if [[ ! "$REASON_ACCOUNT" =~ ^[a-fA-F0-9-]{36}$ ]]; then printf 'Expected a UUID account ID.\n' >&2; exit 1; fi
gcloud run services update reason-api --project="$REASON_PROJECT" --region=us-central1 \
  --update-env-vars="REASON_ACCOUNT_ID=$REASON_ACCOUNT" \
  --update-secrets=ALPACA_PAPER_KEY=alpaca-paper-key:latest,ALPACA_PAPER_SECRET=alpaca-paper-secret:latest
printf 'Read-only paper connection configured. No orders can be placed by this release.\n'
