#!/bin/bash

# Function to log messages in JSON format
log_json() {
    local level=$1
    local message=$2
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}" >&2
}

# Main script
main() {
    # Get required environment variables
    local cluster_name=${CLUSTER_NAME:-}
    local cloud_provider=${CLOUD_PROVIDER:-}
    local account=${ACCOUNT:-}
    local region=${REGION:-}
    local dry_run=${DRY_RUN:-false}
    local verbose=${VERBOSE:-false}

    # Check required arguments
    if [ -z "$cluster_name" ] || [ -z "$cloud_provider" ]; then
        log_json "ERROR" "Missing required arguments. CLUSTER_NAME and CLOUD_PROVIDER must be set."
        exit 1
    fi
    
    # Account is required for GCP
    if [ "$cloud_provider" = "gcp" ] && [ -z "$account" ]; then
        log_json "ERROR" "Missing required argument. ACCOUNT must be set for GCP."
        exit 1
    fi

    # Build command arguments
    local cmd_args=(
        "--cluster-name" "$cluster_name"
        "--cloud" "$cloud_provider"
    )

    # Add account argument if provided (required for GCP, optional for AWS)
    if [ -n "$account" ]; then
        cmd_args+=("--account" "$account")
    fi

    # Add optional arguments
    if [ -n "$region" ]; then
        cmd_args+=("--region" "$region")
    fi
    if [ "$dry_run" = "true" ]; then
        cmd_args+=("--dry-run")
    fi
    if [ "$verbose" = "true" ]; then
        cmd_args+=("--verbose")
    fi

    # Run the Python script with arguments
    python manage_node_groups.py "${cmd_args[@]}"
}

# Execute main function
main "$@" 