terraform {
  required_version = ">= 1.6.0"
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
  }
}
variable "kubeconfig" { type = string }
provider "kubernetes" { config_path = var.kubeconfig }
resource "kubernetes_namespace_v1" "shield" {
  metadata { name = "sim-shield" }
}
# Application manifest, externally managed secrets, PVC, TLS ingress, network policy,
# database, Redis, and artifact provisioning are deployment prerequisites described in RUNBOOK.md.
