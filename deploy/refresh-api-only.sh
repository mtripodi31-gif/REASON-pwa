#!/usr/bin/env bash
# Deploy only REASON's Cloud Run frontend/API. No VM or broker worker changes.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT=reason-512120
REGION=us-central1
SERVICE=reason-api
gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" >/dev/null ||
  { echo "Existing REASON API is missing; stop rather than creating a misconfigured service." >&2; exit 1; }
IMAGE="$REGION-docker.pkg.dev/$PROJECT/reason/reason:auth-$(git rev-parse --short=12 HEAD)"
echo "Building $IMAGE"
gcloud builds submit --project="$PROJECT" --tag="$IMAGE" .
echo "Deploying API image only. Existing service environment, secrets and identity are retained."
gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE" --quiet
URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
python3 deploy/configure_firebase.py "$URL"
curl --fail --silent --show-error "$URL/health"
printf '\nAPI deployed: %s\nThe paper worker VM was NOT restarted or changed.\n' "$URL"
