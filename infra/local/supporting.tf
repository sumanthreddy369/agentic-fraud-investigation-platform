variable "kubeconfig" {
  type        = string
  description = "Absolute path to the isolated kind kubeconfig"
}
resource "kubernetes_deployment_v1" "postgres" {
  metadata {
    name      = "risk-postgres"
    namespace = kubernetes_namespace_v1.risk.metadata[0].name
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "risk-postgres" } }
    template {
      metadata { labels = { app = "risk-postgres" } }
      spec {
        automount_service_account_token = false
        container {
          name  = "postgres"
          image = "postgres:17"
          env_from {
            secret_ref {
              name = "risk-database"
            }
          }
          port { container_port = 5432 }
          resources {
            requests = { cpu = "100m", memory = "128Mi" }
            limits   = { cpu = "1", memory = "512Mi" }
          }
          readiness_probe {
            exec { command = ["pg_isready", "-U", "risk", "-d", "risk"] }
            period_seconds = 5
          }
          volume_mount {
            name       = "database"
            mount_path = "/var/lib/postgresql/data"
          }
        }
        volume {
          name = "database"
          empty_dir {}
        }
      }
    }
  }
}
resource "kubernetes_service_v1" "postgres" {
  metadata {
    name      = "risk-postgres"
    namespace = kubernetes_namespace_v1.risk.metadata[0].name
  }
  spec {
    selector = { app = "risk-postgres" }
    port {
      port        = 5432
      target_port = 5432
    }
  }
}
resource "kubernetes_job_v1" "migrate" {
  depends_on = [kubernetes_deployment_v1.postgres, kubernetes_service_v1.postgres]
  metadata {
    name      = "risk-migrate"
    namespace = kubernetes_namespace_v1.risk.metadata[0].name
  }
  spec {
    backoff_limit = 1
    template {
      metadata {}
      spec {
        restart_policy                  = "Never"
        automount_service_account_token = false
        container {
          name              = "migrate"
          image             = var.image
          image_pull_policy = "IfNotPresent"
          command           = ["/opt/venv/bin/alembic", "upgrade", "head"]
          env_from {
            secret_ref {
              name = "risk-runtime"
            }
          }
        }
      }
    }
  }
  wait_for_completion = true
  timeouts { create = "5m" }
}
