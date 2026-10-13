terraform {
  required_version = ">= 1.8, < 2.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
  }
}

# Deliberately targets the local cluster, never the user's active cloud context.
provider "kubernetes" {
  config_path    = var.kubeconfig
  config_context = "kind-risk-proof"
}

variable "image" {
  type        = string
  description = "Locally built image tag, or approved immutable image digest."
}

variable "replicas" {
  type    = number
  default = 1
  validation {
    condition     = contains([1, 2, 3], var.replicas)
    error_message = "The local learning deployment permits one to three replicas."
  }
}

resource "kubernetes_namespace_v1" "risk" {
  metadata { name = "risk-learning" }
}

# Credentials and model artifacts are provisioned separately, outside Terraform state.
# Secret risk-runtime: RISK_API_TOKEN and RISK_DATABASE_URL.
# kind host mount: verified ONNX model and manifest.json, mounted read-only.
resource "kubernetes_deployment_v1" "api" {
  depends_on = [kubernetes_job_v1.migrate]
  metadata {
    name      = "risk-api"
    namespace = kubernetes_namespace_v1.risk.metadata[0].name
  }
  spec {
    replicas = var.replicas
    selector { match_labels = { app = "risk-api" } }
    template {
      metadata { labels = { app = "risk-api" } }
      spec {
        automount_service_account_token = false
        security_context {
          run_as_non_root = true
          run_as_user     = 10001
          run_as_group    = 10001
          fs_group        = 10001
        }
        container {
          name              = "api"
          image             = var.image
          image_pull_policy = "IfNotPresent"
          port { container_port = 8000 }
          env_from {
            secret_ref {
              name = "risk-runtime"
            }
          }
          env {
            name  = "RISK_ALLOWED_HOSTS"
            value = "[\"localhost\",\"127.0.0.1\",\"risk-api\"]"
          }
          env {
            name  = "RISK_ONNX_MANIFESTS"
            value = "{\"ieee_cis\":\"/models/manifest.json\"}"
          }
          env {
            name  = "RISK_DOCS_ENABLED"
            value = "false"
          }
          resources {
            requests = { cpu = "250m", memory = "256Mi" }
            limits   = { cpu = "1", memory = "1Gi" }
          }
          security_context {
            allow_privilege_escalation = false
            read_only_root_filesystem  = true
            capabilities { drop = ["ALL"] }
          }
          volume_mount {
            name       = "models"
            mount_path = "/models"
            read_only  = true
          }
          liveness_probe {
            http_get {
              path = "/health/live"
              port = 8000
              http_header {
                name  = "Host"
                value = "localhost"
              }
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }
          readiness_probe {
            http_get {
              path = "/health/ready"
              port = 8000
              http_header {
                name  = "Host"
                value = "localhost"
              }
            }
            period_seconds = 5
          }
        }
        volume {
          name = "models"
          host_path { path = "/risk-models/model-v2" }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "risk-api"
    namespace = kubernetes_namespace_v1.risk.metadata[0].name
  }
  spec {
    selector = { app = "risk-api" }
    type     = "ClusterIP"
    port {
      port        = 8000
      target_port = 8000
    }
  }
}
