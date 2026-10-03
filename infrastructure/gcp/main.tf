terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
  default     = "rai-discord-bot"
}

variable "region" {
  description = "Default Google Cloud Region"
  type        = string
  default     = "us-central1"
}

variable "alert_email" {
  description = "Email address for monitoring outage alerts"
  type        = string
  default     = ""
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Enable Required Services
resource "google_project_service" "firestore" {
  project = var.project_id
  service = "firestore.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "monitoring" {
  project = var.project_id
  service = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  project = var.project_id
  service = "iam.googleapis.com"
  disable_on_destroy = false
}

# 2. Firestore Native Database
resource "google_firestore_database" "database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.firestore]
}

# 3. Service Account for RAI Cloud Sync
resource "google_service_account" "rai_sync" {
  account_id   = "rai-bot-sync"
  display_name = "RAI Discord Bot Cloud Sync Service Account"
  depends_on   = [google_project_service.iam]
}

resource "google_project_iam_member" "datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.rai_sync.email}"
}

# 4. Service Account Key
resource "google_service_account_key" "rai_sync_key" {
  service_account_id = google_service_account.rai_sync.name
}

# 5. Output Service Account Key locally
resource "local_file" "service_account_credentials" {
  content  = base64decode(google_service_account_key.rai_sync_key.private_key)
  filename = "${path.module}/../../config/firebase_credentials.json"
}

# 6. Cloud Monitoring Alert Policy
resource "google_monitoring_alert_policy" "firestore_error_alert" {
  display_name = "『RΛI』 High Cloud Sync Error Rate"
  combiner     = "OR"
  conditions {
    display_name = "Firestore Server Error Spike"
    condition_threshold {
      filter          = "resource.type = \"firestore_instance\" AND metric.type = \"firestore.googleapis.com/network/server_error_count\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  depends_on = [google_project_service.monitoring]
}
