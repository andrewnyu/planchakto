#!/usr/bin/env bash
# Build the container on Cloud Build and deploy it to Cloud Run.
# Prerequisites (one-time, see README "Docker and deployment"): project with billing, APIs enabled,
# Firestore (native), private bucket, Artifact Registry repo "buildgraph", runtime service account.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT=${PROJECT:-planchakto}
REGION=${REGION:-asia-southeast1}
SERVICE=${SERVICE:-buildgraph}
BUCKET=${BUCKET:-$PROJECT-artifacts}
GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.8-flash}
# Drawings (multimodal) go to the larger model: Flash garbled sketch dimensions that Pro read exactly.
GEMINI_VISION_MODEL=${GEMINI_VISION_MODEL:-gemini-3.1-pro-preview}
SA=buildgraph-runtime@$PROJECT.iam.gserviceaccount.com
IMAGE=$REGION-docker.pkg.dev/$PROJECT/buildgraph/app:$(git rev-parse --short HEAD)$(git diff --quiet || echo -dirty)

# Source upload honours .gitignore, so .env, .data and node_modules never leave this machine.
gcloud builds submit --project "$PROJECT" --tag "$IMAGE" .
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
  --service-account "$SA" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --concurrency 8 --timeout 120 --min-instances 0 --max-instances 2 \
  --set-env-vars "BUILDGRAPH_STORAGE=google,GOOGLE_CLOUD_PROJECT=$PROJECT,BUILDGRAPH_BUCKET=$BUCKET,BUILDGRAPH_WORKSPACE=demo,BUILDGRAPH_AI_PROVIDER=vertex,GEMINI_MODEL=$GEMINI_MODEL,GEMINI_VISION_MODEL=$GEMINI_VISION_MODEL,GOOGLE_CLOUD_LOCATION=global,OPENBLAS_NUM_THREADS=1"
URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')
echo "Deployed: $URL"
curl -fsS "$URL/api/health" && echo
