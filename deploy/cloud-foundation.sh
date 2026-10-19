#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
REASON_PROJECT='reason-512120'
REASON_REGION='us-central1'
printf 'Deploying REASON read-only foundation to %s. No trading worker or brokerage writes.\n' "$REASON_PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com identitytoolkit.googleapis.com firebase.googleapis.com firebaserules.googleapis.com --project="$REASON_PROJECT"
# Confirm dedicated project and pre-created database/identity rather than touching Direct Line.
gcloud firestore databases describe --database='(default)' --project="$REASON_PROJECT" --format='value(locationId)'
gcloud iam service-accounts describe "reason-api@$REASON_PROJECT.iam.gserviceaccount.com" --project="$REASON_PROJECT" --format='value(email)'
python3 deploy/configure_firebase.py
# Auth revocation checks need user-read permission, separate from database access.
gcloud projects add-iam-policy-binding "$REASON_PROJECT" --member="serviceAccount:reason-api@$REASON_PROJECT.iam.gserviceaccount.com" --role=roles/firebaseauth.viewer --condition=None --quiet >/dev/null
# Dedicated build identity has build permissions but no broker secrets.
if ! gcloud iam service-accounts describe "reason-build@$REASON_PROJECT.iam.gserviceaccount.com" --project="$REASON_PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create reason-build --project="$REASON_PROJECT" --display-name='REASON image builder'
fi
gcloud projects add-iam-policy-binding "$REASON_PROJECT" --member="serviceAccount:reason-build@$REASON_PROJECT.iam.gserviceaccount.com" --role=roles/run.builder --condition=None --quiet >/dev/null
# Public app shell is necessary for Google sign-in; every private API verifies the owner.
gcloud run deploy reason-api --project="$REASON_PROJECT" --region="$REASON_REGION" --source=. \
  --service-account="reason-api@$REASON_PROJECT.iam.gserviceaccount.com" \
  --build-service-account="projects/$REASON_PROJECT/serviceAccounts/reason-build@$REASON_PROJECT.iam.gserviceaccount.com" \
  --env-vars-file=deploy/runtime.env.yaml --allow-unauthenticated --min-instances=0 --max-instances=2 --memory=512Mi --cpu=1 --timeout=60 --quiet
REASON_URL="$(gcloud run services describe reason-api --project="$REASON_PROJECT" --region="$REASON_REGION" --format='value(status.url)')"
python3 deploy/configure_firebase.py "$REASON_URL"
if ! curl --fail --silent --show-error "$REASON_URL/health"; then
  printf '\nThe container deployed, but public HTTP access is not verified. Check Cloud Run IAM and ingress before continuing.\n' >&2
  exit 1
fi
printf '\nOpen REASON: %s\nSign in using tripodi@directlinemedical.app. Broker connection is not configured yet.\n' "$REASON_URL"
