#!/usr/bin/env bash
# ==============================================================================
# 『RΛI』 Google Cloud & Firebase Automated Setup Script
# Run directly in Google Cloud Shell (top-right '>_' icon in GCP Console)
# Project: rai-discord-bot
# ==============================================================================

set -euo pipefail

PROJECT_ID="rai-discord-bot"
REGION="us-central1"
SA_NAME="rai-bot-sync"
SA_DISPLAY="RAI Discord Bot Cloud Sync Service Account"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="firebase_credentials.json"

echo "============================================================"
echo "『RΛI』 • STARTING AUTOMATED GCP & FIREBASE PROVISIONING"
echo "Project ID: ${PROJECT_ID}"
echo "============================================================"

# 1. Set active project
echo "[1/6] Configuring gcloud project..."
gcloud config set project "${PROJECT_ID}" --quiet

# 2. Enable necessary Google Cloud APIs
echo "[2/6] Enabling APIs (Firestore, Monitoring, Logging, IAM)..."
gcloud services enable \
    firestore.googleapis.com \
    monitoring.googleapis.com \
    logging.googleapis.com \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com \
    --quiet

# 3. Create Firestore Database (Native mode) if not exists
echo "[3/6] Checking Firestore Database..."
if ! gcloud firestore databases describe --database="(default)" &>/dev/null; then
    echo "Creating Cloud Firestore database in Native mode (${REGION})..."
    gcloud firestore databases create \
        --location="${REGION}" \
        --type=firestore-native \
        --quiet || true
else
    echo "Firestore database '(default)' already exists."
fi

# 4. Create Service Account and assign IAM permissions
echo "[4/6] Creating Service Account for RAI Cloud Synchronization..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null; then
    gcloud iam service-accounts create "${SA_NAME}" \
        --display-name="${SA_DISPLAY}" \
        --quiet
fi

# Grant Cloud Datastore User (Firestore Read/Write) role
echo "Assigning Firestore Datastore User role..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/datastore.user" \
    --quiet

# Grant Cloud Monitoring Metric Writer (optional for direct metric streaming)
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/monitoring.metricWriter" \
    --quiet

# 5. Generate Service Account Key JSON
echo "[5/6] Generating Service Account Key..."
gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${SA_EMAIL}" \
    --quiet

# 6. Create Cloud Monitoring Alert Policy for Firestore Errors
echo "[6/6] Creating Cloud Monitoring Alert Policy..."
cat << 'EOF' > /tmp/rai_alert_policy.json
{
  "displayName": "『RΛI』 High Cloud Sync & Firestore Error Rate",
  "documentation": {
    "content": "Alert triggered when Firestore document read/write error count spikes on rai-discord-bot.",
    "mimeType": "text/markdown"
  },
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Firestore Request Errors",
      "conditionThreshold": {
        "filter": "resource.type = \"firestore_instance\" AND metric.type = \"firestore.googleapis.com/network/server_error_count\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 5,
        "duration": "60s",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_RATE"
          }
        ]
      }
    }
  ],
  "enabled": true
}
EOF

if gcloud alpha monitoring policies create --policy-from-file=/tmp/rai_alert_policy.json &>/dev/null; then
    echo "Monitoring Alert Policy created successfully."
else
    echo "Alert policy registered or already exists."
fi

echo "============================================================"
echo "『RΛI』 • PROVISIONING COMPLETE!"
echo "============================================================"
echo ""
echo "Your Service Account Key has been generated in: ${KEY_FILE}"
echo ""
echo "TO DOWNLOAD THIS FILE TO YOUR LOCAL COMPUTER:"
echo "1. Run this command in Cloud Shell:"
echo "   cloudshell download ${KEY_FILE}"
echo "2. Place the downloaded file into your bot's folder at:"
echo "   f:\\Bot\\config\\firebase_credentials.json"
echo ""
echo "============================================================"
