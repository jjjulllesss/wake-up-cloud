#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to log messages in JSON format
log_json() {
    local level=$1
    local message=$2
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}" >&2
}

# Function to detect cloud provider with detailed checks
detect_cloud_provider() {
    # AWS Detection
    if [ -n "$AWS_CLOUD_SHELL" ]; then
        log_json "DEBUG" "Detected AWS CloudShell environment" >&2
        echo "aws"
        return 0
    fi

    # Check for AWS credentials
    if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
        log_json "DEBUG" "Detected AWS credentials in environment" >&2
        echo "aws"
        return 0
    fi

    # Check for AWS CLI configuration
    if [ -d "/home/appuser/.aws" ] && [ -f "/home/appuser/.aws/credentials" ]; then
        log_json "DEBUG" "Detected AWS CLI configuration" >&2
        echo "aws"
        return 0
    fi

    # GCP Detection
    if [ -n "$CLOUD_SHELL" ]; then
        log_json "DEBUG" "Detected Google Cloud Shell environment" >&2
        echo "gcp"
        return 0
    fi

    # Check for GCP credentials
    if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        log_json "DEBUG" "Detected GCP credentials in environment" >&2
        echo "gcp"
        return 0
    fi

    # Check for gcloud configuration
    if [ -d "/home/appuser/.config/gcloud" ]; then
        log_json "DEBUG" "Detected gcloud configuration" >&2
        echo "gcp"
        return 0
    fi

    # Check for GCP metadata server (if running on GCP)
    if curl -s -f -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/id" > /dev/null 2>&1; then
        log_json "DEBUG" "Detected GCP metadata server" >&2
        echo "gcp"
        return 0
    fi

    # Check for AWS metadata server (if running on AWS)
    if curl -s -f "http://169.254.169.254/latest/meta-data/instance-id" > /dev/null 2>&1; then
        log_json "DEBUG" "Detected AWS metadata server" >&2
        echo "aws"
        return 0
    fi

    # If no cloud provider detected
    log_json "WARNING" "Could not detect cloud provider environment" >&2
    echo "unknown"
    return 1
}

# Function to validate cloud provider
validate_cloud_provider() {
    local provider=$1
    
    case "$provider" in
        aws)
            # Additional AWS validation
            if ! aws sts get-caller-identity > /dev/null 2>&1; then
                log_json "ERROR" "AWS credentials validation failed"
                return 1
            fi
            log_json "INFO" "AWS credentials validated successfully"
            ;;
        gcp)
            # Additional GCP validation
            if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" > /dev/null 2>&1; then
                log_json "ERROR" "GCP credentials validation failed"
                return 1
            fi
            log_json "INFO" "GCP credentials validated successfully"
            ;;
        *)
            log_json "ERROR" "Invalid cloud provider: $provider"
            return 1
            ;;
    esac
    
    return 0
}

# Function to setup logging
setup_logging() {
    LOG_DIR="/tmp/node_group_manager"
    mkdir -p "$LOG_DIR"
    
    # Create log file with timestamp
    LOG_FILE="$LOG_DIR/node_group_manager_$(date +%Y%m%d_%H%M%S).log"
    
    # Set up log rotation (keep last 5 logs)
    find "$LOG_DIR" -name "node_group_manager_*.log" -type f | sort -r | tail -n +6 | xargs rm -f 2>/dev/null
    
    # Log environment information
    log_json "INFO" "Logging started"
    log_json "INFO" "Log file: $LOG_FILE"
    
    # Log environment information
    detected_provider=$(detect_cloud_provider)
    log_json "INFO" "Cloud provider: $detected_provider"
    log_json "INFO" "Python version: $(python --version 2>&1)"
    log_json "INFO" "Working directory: $(pwd)"
}

# Main script
main() {
    # Setup logging
    setup_logging

    # Get cloud provider from command line arguments
    cloud_provider=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cloud)
                cloud_provider="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # If cloud provider not specified, try to detect it
    if [ -z "$cloud_provider" ]; then
        cloud_provider=$(detect_cloud_provider)
    fi

    # Validate cloud provider
    if ! validate_cloud_provider "$cloud_provider"; then
        log_json "ERROR" "Cloud provider validation failed"
        exit 1
    fi

    # Run the Python script with all arguments
    python manage_node_groups.py "$@"
}

# Execute main function with all arguments
main "$@" 