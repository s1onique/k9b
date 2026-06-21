#!/usr/bin/env bash
# =============================================================================
# k9b CNPG Live Lab RBAC Preflight
#
# Verifies Kubernetes permissions required for the live lab.
# Fails closed with actionable output identifying missing permissions.
#
# Usage:
#   k9b_cnpg_live_lab_rbac_preflight.sh cluster           # Cluster-scoped checks
#   k9b_cnpg_live_lab_rbac_preflight.sh namespace <ns>    # Namespace-scoped checks
#
# Exit codes:
#   0 - All checks passed
#   1 - Missing permissions detected
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Helper function for RBAC checks
# -----------------------------------------------------------------------------
check_can_i() {
    local description="$1"
    shift

    printf 'Checking: %s ... ' "$description"
    if kubectl auth can-i "$@" --quiet 2>/dev/null; then
        echo "YES"
        return 0
    else
        echo "NO"
        echo "ERROR: missing permission for: $description"
        echo "Command: kubectl auth can-i $* --quiet"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Print current Kubernetes subject (no token leakage)
# -----------------------------------------------------------------------------
print_subject_diagnostics() {
    echo "=== Kubernetes Subject Diagnostics ==="

    # Print service account namespace from mounted file
    local sa_dir="/var/run/secrets/kubernetes.io/serviceaccount"
    if [ -f "$sa_dir/namespace" ]; then
        echo "ServiceAccount namespace: $(cat "$sa_dir/namespace")"
    else
        echo "ServiceAccount namespace: (not available)"
    fi

    # Print current context
    echo "Current context: $(kubectl config current-context 2>/dev/null || echo 'unknown')"

    # Try kubectl auth whoami (fails gracefully if unsupported)
    echo "Authenticated subject:"
    if kubectl auth whoami 2>/dev/null; then
        echo "Subject info captured"
    else
        echo "(kubectl auth whoami not supported or no permissions)"
    fi

    echo "=== End Subject Diagnostics ==="
}

# -----------------------------------------------------------------------------
# Cluster-scoped RBAC checks
# -----------------------------------------------------------------------------
run_cluster_checks() {
    echo "=== Verifying cluster-scoped Kubernetes permissions ==="

    local failed=0

    check_can_i "get pods across all namespaces" get pods --all-namespaces || failed=$((failed + 1))
    check_can_i "get nodes" get nodes || failed=$((failed + 1))
    check_can_i "get CNPG Cluster CRD" get crd clusters.postgresql.cnpg.io || failed=$((failed + 1))
    check_can_i "get CNPG operator pods" get pods -n cnpg-system || failed=$((failed + 1))
    check_can_i "get CNPG operator deployments" get deployments -n cnpg-system || failed=$((failed + 1))
    check_can_i "create namespaces" create namespaces || failed=$((failed + 1))
    check_can_i "delete namespaces" delete namespaces || failed=$((failed + 1))

    if [ $failed -gt 0 ]; then
        echo ""
        echo "Kubernetes permission preflight FAILED: $failed check(s) missing permissions"
        return 1
    fi

    echo ""
    echo "Kubernetes permission preflight PASSED"
    return 0
}

# -----------------------------------------------------------------------------
# Namespace-scoped RBAC checks
# -----------------------------------------------------------------------------
run_namespace_checks() {
    local namespace="$1"

    echo "=== Verifying namespace-scoped Kubernetes permissions for: $namespace ==="

    local failed=0

    # Core workload permissions
    check_can_i "create pods in lab namespace" create pods -n "$namespace" || failed=$((failed + 1))
    check_can_i "delete pods in lab namespace" delete pods -n "$namespace" || failed=$((failed + 1))
    check_can_i "list pods in lab namespace" list pods -n "$namespace" || failed=$((failed + 1))
    check_can_i "get pods/log in lab namespace" get pods/log -n "$namespace" || failed=$((failed + 1))

    # Event and service visibility
    check_can_i "get events in lab namespace" get events -n "$namespace" || failed=$((failed + 1))
    check_can_i "get services in lab namespace" get services -n "$namespace" || failed=$((failed + 1))

    # Workload controllers
    check_can_i "get deployments in lab namespace" get deployments.apps -n "$namespace" || failed=$((failed + 1))
    check_can_i "get statefulsets in lab namespace" get statefulsets.apps -n "$namespace" || failed=$((failed + 1))

    # Config and secrets for Helm
    check_can_i "create configmaps in lab namespace" create configmaps -n "$namespace" || failed=$((failed + 1))
    check_can_i "create secrets in lab namespace" create secrets -n "$namespace" || failed=$((failed + 1))

    # CNPG Cluster CRD
    check_can_i "create CNPG clusters in lab namespace" create clusters.postgresql.cnpg.io -n "$namespace" || failed=$((failed + 1))
    check_can_i "get CNPG clusters in lab namespace" get clusters.postgresql.cnpg.io -n "$namespace" || failed=$((failed + 1))

    # Jobs (may be needed by Helm charts)
    check_can_i "get jobs in lab namespace" get jobs.batch -n "$namespace" || failed=$((failed + 1))

    if [ $failed -gt 0 ]; then
        echo ""
        echo "Namespace-scoped permission preflight FAILED: $failed check(s) missing permissions"
        return 1
    fi

    echo ""
    echo "Namespace-scoped permission preflight PASSED"
    return 0
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    local mode="${1:-}"
    local namespace="${2:-}"

    if [ -z "$mode" ]; then
        echo "Usage: $0 <cluster|namespace> [namespace]"
        echo "  cluster              - Run cluster-scoped RBAC checks"
        echo "  namespace <ns>       - Run namespace-scoped RBAC checks"
        exit 1
    fi

    case "$mode" in
        cluster)
            print_subject_diagnostics
            run_cluster_checks
            ;;
        namespace)
            if [ -z "$namespace" ]; then
                echo "ERROR: namespace mode requires a namespace argument"
                exit 1
            fi
            run_namespace_checks "$namespace"
            ;;
        subject)
            print_subject_diagnostics
            ;;
        *)
            echo "ERROR: unknown mode: $mode"
            echo "Usage: $0 <cluster|namespace> [namespace]"
            exit 1
            ;;
    esac
}

main "$@"