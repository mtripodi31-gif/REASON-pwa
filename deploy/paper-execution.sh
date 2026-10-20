#!/usr/bin/env bash
# Build and deploy the PAPER-only API plus one persistent e2-small worker.
set -euo pipefail
cd "$(dirname "$0")/.."
REASON_PROJECT='reason-512120'
REASON_REGION='us-central1'
REASON_ZONE='us-central1-a'
REASON_REPOSITORY='reason'
REASON_IMAGE="$REASON_REGION-docker.pkg.dev/$REASON_PROJECT/$REASON_REPOSITORY/reason:paper-execution-0-3"
REASON_API="reason-api@$REASON_PROJECT.iam.gserviceaccount.com"
REASON_WORKER="reason-worker@$REASON_PROJECT.iam.gserviceaccount.com"

if [ ! -f deploy/runtime.env.yaml ]; then
  printf 'Missing deploy/runtime.env.yaml. Run deploy/cloud-foundation.sh first.\n' >&2
  exit 1
fi
# Older connect-paper releases set the account ID on Cloud Run without updating
# the ignored local runtime file. Recover that non-secret binding automatically.
if ! grep -q '^REASON_ACCOUNT_ID:' deploy/runtime.env.yaml; then
  REASON_EXISTING="$(gcloud run services describe reason-api --project="$REASON_PROJECT" --region="$REASON_REGION" --format=json 2>/dev/null | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="REASON_ACCOUNT_ID") | .value' | head -n 1)"
  if [[ "$REASON_EXISTING" =~ ^[a-fA-F0-9-]{36}$ ]]; then
    printf 'REASON_ACCOUNT_ID: "%s"\n' "$REASON_EXISTING" >> deploy/runtime.env.yaml
  else
    printf 'Missing paper account binding. Run deploy/connect-paper.sh first.\n' >&2
    exit 1
  fi
fi
REASON_ACCOUNT="$(sed -n 's/^REASON_ACCOUNT_ID:[[:space:]]*"\{0,1\}\([^"[:space:]]*\)"\{0,1\}$/\1/p' deploy/runtime.env.yaml)"
if [[ ! "$REASON_ACCOUNT" =~ ^[a-fA-F0-9-]{36}$ ]]; then
  printf 'The local REASON_ACCOUNT_ID is invalid. Run deploy/connect-paper.sh again.\n' >&2
  exit 1
fi
read -r -p 'Confirm the old Mac REASON process cannot restart. Type STOPPED: ' REASON_CONFIRM
if [ "$REASON_CONFIRM" != 'STOPPED' ]; then printf 'Stopped before enabling a second account controller.\n' >&2; exit 1; fi

gcloud config set project "$REASON_PROJECT" >/dev/null
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com run.googleapis.com firestore.googleapis.com secretmanager.googleapis.com --project="$REASON_PROJECT"
if ! gcloud artifacts repositories describe "$REASON_REPOSITORY" --location="$REASON_REGION" --project="$REASON_PROJECT" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REASON_REPOSITORY" --repository-format=docker --location="$REASON_REGION" --project="$REASON_PROJECT" --description='REASON paper images'
fi
if ! gcloud iam service-accounts describe "$REASON_WORKER" --project="$REASON_PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create reason-worker --project="$REASON_PROJECT" --display-name='REASON paper execution worker'
fi
for REASON_ROLE in roles/datastore.user roles/artifactregistry.reader roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "$REASON_PROJECT" --member="serviceAccount:$REASON_WORKER" --role="$REASON_ROLE" --condition=None --quiet >/dev/null
done
for REASON_SECRET in alpaca-paper-key alpaca-paper-secret; do
  gcloud secrets add-iam-policy-binding "$REASON_SECRET" --project="$REASON_PROJECT" --member="serviceAccount:$REASON_WORKER" --role=roles/secretmanager.secretAccessor --condition=None --quiet >/dev/null
done

gcloud builds submit --project="$REASON_PROJECT" --tag="$REASON_IMAGE" .
gcloud run deploy reason-api --project="$REASON_PROJECT" --region="$REASON_REGION" --image="$REASON_IMAGE" \
  --service-account="$REASON_API" --env-vars-file=deploy/runtime.env.yaml \
  --update-secrets=ALPACA_PAPER_KEY=alpaca-paper-key:latest,ALPACA_PAPER_SECRET=alpaca-paper-secret:latest \
  --no-invoker-iam-check --min-instances=0 --max-instances=2 --memory=512Mi --cpu=1 --timeout=60 --quiet

REASON_STARTUP="$(mktemp)"
trap 'rm -f "$REASON_STARTUP"' EXIT
sed -e "s|__IMAGE__|$REASON_IMAGE|g" -e "s|__PROJECT__|$REASON_PROJECT|g" -e "s|__ACCOUNT__|$REASON_ACCOUNT|g" > "$REASON_STARTUP" <<'WORKER'
#!/bin/bash
set -eu
docker-credential-gcr configure-docker --registries=us-central1-docker.pkg.dev
docker pull __IMAGE__
docker rm -f reason-worker >/dev/null 2>&1 || true
docker run -d --restart=always --name=reason-worker \
  -e GOOGLE_CLOUD_PROJECT=__PROJECT__ \
  -e REASON_ACCOUNT_ID=__ACCOUNT__ \
  -e REASON_EXECUTION_ENABLED=true \
  -e REASON_MARKET_DATA_FEED=iex \
  __IMAGE__ python -m reason.paper
WORKER

if gcloud compute instances describe reason-worker-1 --zone="$REASON_ZONE" --project="$REASON_PROJECT" >/dev/null 2>&1; then
  gcloud compute instances add-metadata reason-worker-1 --zone="$REASON_ZONE" --project="$REASON_PROJECT" --metadata-from-file=startup-script="$REASON_STARTUP"
  gcloud compute instances reset reason-worker-1 --zone="$REASON_ZONE" --project="$REASON_PROJECT"
else
  gcloud compute instances create reason-worker-1 --project="$REASON_PROJECT" --zone="$REASON_ZONE" \
    --machine-type=e2-small --boot-disk-size=20GB --image-family=cos-stable --image-project=cos-cloud \
    --service-account="$REASON_WORKER" --scopes=cloud-platform --metadata-from-file=startup-script="$REASON_STARTUP"
fi

REASON_URL="$(gcloud run services describe reason-api --project="$REASON_PROJECT" --region="$REASON_REGION" --format='value(status.url)')"
python3 deploy/configure_firebase.py "$REASON_URL"
curl --fail --silent --show-error "$REASON_URL/health"
printf '\nREASON paper execution 0.3 deployed. Open: %s\nThe worker starts with new entries paused until a valid Trade Card is activated or Resume is pressed.\n' "$REASON_URL"
