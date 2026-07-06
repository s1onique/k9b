#!/bin/bash
# kubectl-based trace extraction from in-cluster OTel Collector
#
# This script copies trace files from the OTel Collector pod to local artifacts.
# It bridges the gap between in-cluster Collector traces and local trace-capture.
#
# Prerequisites:
#   - kubectl configured with access to the k9b namespace
#   - OTel Collector running with file exporter configured
#   - emptyDir volume mounted at /var/lib/k9b-traces in the Collector pod
#
# Usage:
#   ./copy_collector_traces.sh [--namespace k9b] [--collector-name otel-collector] [--output-dir ./trace-capture]
#
# Environment:
#   K9B_NAMESPACE - Override namespace (default: k9b)
#   COLLECTOR_NAME - Override Collector deployment name (default: otel-collector)
#   OUTPUT_DIR - Override output directory (default: ./)

set -euo pipefail

# Defaults
NAMESPACE="${K9B_NAMESPACE:-k9b}"
COLLECTOR_NAME="${COLLECTOR_NAME:-}"
OUTPUT_DIR="${OUTPUT_DIR:-.}"
TRACE_PATH="/var/lib/k9b-traces/collector-traces.jsonl"
VERBOSE="${VERBOSE:-0}"

# Usage message
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Copy trace files from OTel Collector pod to local artifacts.

OPTIONS:
    -n, --namespace NAMESPACE   Kubernetes namespace (default: k9b)
    -c, --collector-name NAME   Collector deployment/service name (default: auto-detect)
    -o, --output-dir DIR        Output directory (default: .)
    -p, --trace-path PATH       Path inside Collector pod (default: /var/lib/k9b-traces/collector-traces.jsonl)
    -v, --verbose               Verbose output
    -h, --help                  Show this help

ENVIRONMENT:
    K9B_NAMESPACE    Override namespace
    COLLECTOR_NAME   Override collector name
    OUTPUT_DIR       Override output directory

EXAMPLES:
    # Copy traces from default setup:
    ./copy_collector_traces.sh

    # Copy to specific directory:
    ./copy_collector_traces.sh -o ./trace-capture/index-perf-proof/enabled

    # With custom namespace:
    K9B_NAMESPACE=my-namespace ./copy_collector_traces.sh
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -c|--collector-name)
            COLLECTOR_NAME="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -p|--trace-path)
            TRACE_PATH="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Verbose helper
log() {
    if [[ "$VERBOSE" == "1" ]]; then
        echo "[INFO] $*"
    fi
}

warn() {
    echo "[WARN] $*" >&2
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

# Find Collector pod if name not specified
find_collector_pod() {
    if [[ -n "$COLLECTOR_NAME" ]]; then
        # Try deployment first, then statefulset, then service
        local pod
        pod=$(kubectl get pod -n "$NAMESPACE" -l "app=$COLLECTOR_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
        if [[ -z "$pod" ]]; then
            pod=$(kubectl get pod -n "$NAMESPACE" -l "app.kubernetes.io/name=$COLLECTOR_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
        fi
        echo "$pod"
    else
        # Auto-detect: look for common patterns
        local pod
        # Pattern 1: app=otel-collector
        pod=$(kubectl get pod -n "$NAMESPACE" -l "app=otel-collector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
        if [[ -z "$pod" ]]; then
            # Pattern 2: app.kubernetes.io/name=opentelemetry-collector
            pod=$(kubectl get pod -n "$NAMESPACE" -l "app.kubernetes.io/name=opentelemetry-collector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
        fi
        if [[ -z "$pod" ]]; then
            # Pattern 3: any pod with otel-collector in name
            pod=$(kubectl get pod -n "$NAMESPACE" -o jsonpath='{.items[?(@.metadata.name =~ ".*otel.*collector.*")].metadata.name}' 2>/dev/null | awk '{print $1}' || true)
        fi
        echo "$pod"
    fi
}

# Check if trace file exists in pod
check_trace_file() {
    local pod="$1"
    local path="$2"
    kubectl exec -n "$NAMESPACE" "$pod" -- test -f "$path" 2>/dev/null
}

# Get trace file size
get_trace_file_size() {
    local pod="$1"
    local path="$2"
    kubectl exec -n "$NAMESPACE" "$pod" -- stat -c%s "$path" 2>/dev/null || echo "0"
}

# Main logic
main() {
    log "Namespace: $NAMESPACE"
    log "Trace path: $TRACE_PATH"
    log "Output dir: $OUTPUT_DIR"

    # Find Collector pod
    local collector_pod
    collector_pod=$(find_collector_pod)
    if [[ -z "$collector_pod" ]]; then
        error "Could not find OTel Collector pod in namespace $NAMESPACE. Available options:"
        error "  - Set COLLECTOR_NAME environment variable"
        error "  - Check that Collector is running with kubectl get pods -n $NAMESPACE"
    fi

    log "Found Collector pod: $collector_pod"

    # Check if trace file exists
    if ! check_trace_file "$collector_pod" "$TRACE_PATH"; then
        warn "Trace file not found at $TRACE_PATH in pod $collector_pod"
        warn "Ensure the Collector is configured with file exporter pointing to this path."
        warn "See: collector-config-k8s.yaml"
        exit 1
    fi

    local file_size
    file_size=$(get_trace_file_size "$collector_pod" "$TRACE_PATH")
    log "Trace file size: $file_size bytes"

    if [[ "$file_size" == "0" ]]; then
        warn "Trace file is empty. No traces captured yet."
        warn "Make sure the k9b backend is sending traces to the Collector."
        exit 0
    fi

    # Create output directory
    mkdir -p "$OUTPUT_DIR"

    # Generate output filename with timestamp
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local output_file="$OUTPUT_DIR/collector-traces-$timestamp.jsonl"

    log "Copying traces to $output_file..."

    # Copy the file
    kubectl cp "${NAMESPACE}/${collector_pod}:${TRACE_PATH}" "$output_file"

    log "Successfully copied traces to $output_file"

    # Also copy as latest
    local latest_file="$OUTPUT_DIR/collector-traces-latest.jsonl"
    cp "$output_file" "$latest_file"
    log "Also available as: $latest_file"

    # Print summary
    local line_count
    line_count=$(wc -l < "$output_file")
    echo ""
    echo "Trace extraction complete:"
    echo "  Pod: $collector_pod"
    echo "  Source: $TRACE_PATH"
    echo "  Size: $file_size bytes"
    echo "  Lines: $line_count"
    echo "  Output: $output_file"
    echo "  Latest: $latest_file"
}

main "$@"
