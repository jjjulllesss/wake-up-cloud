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
    # Get cloud provider from environment
    local cloud_provider=${CLOUD_PROVIDER:-}
    if [ -z "$cloud_provider" ]; then
        log_json "ERROR" "CLOUD_PROVIDER environment variable not set"
        exit 1
    fi

    # Run the Python script with all arguments
    python manage_node_groups.py "$@"
}

# Execute main function with all arguments
main "$@" 