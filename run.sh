#!/bin/bash

# Function to log messages in JSON format
log_json() {
    local level=$1
    local message=$2
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}"
}

# Function to detect cloud provider with detailed checks
detect_cloud_provider() {
    # AWS Detection
    if [ -n "$AWS_CLOUD_SHELL" ]; then
        log_json "DEBUG" "Detected AWS CloudShell environment"
        echo "aws"
        return 0
    fi

    # Check for AWS credentials
    if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
        log_json "DEBUG" "Detected AWS credentials in environment"
        if [ -n "$AWS_SESSION_TOKEN" ]; then
            log_json "DEBUG" "Detected AWS session token in environment"
        fi
        echo "aws"
        return 0
    fi

    # Check for AWS CLI configuration
    if [ -d "/home/appuser/.aws" ] && [ -f "/home/appuser/.aws/credentials" ]; then
        log_json "DEBUG" "Detected AWS CLI configuration"
        echo "aws"
        return 0
    fi

    # GCP Detection
    if [ -n "$CLOUD_SHELL" ]; then
        log_json "DEBUG" "Detected Google Cloud Shell environment"
        echo "gcp"
        return 0
    fi

    # Check for GCP credentials
    if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        log_json "DEBUG" "Detected GCP credentials in environment"
        echo "gcp"
        return 0
    fi

    # Check for gcloud configuration
    if [ -d "/home/appuser/.config/gcloud" ]; then
        log_json "DEBUG" "Detected gcloud configuration"
        echo "gcp"
        return 0
    fi

    # Check for GCP metadata server (if running on GCP)
    if curl -s -f -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/id" > /dev/null 2>&1; then
        log_json "DEBUG" "Detected GCP metadata server"
        echo "gcp"
        return 0
    fi

    # Check for AWS metadata server (if running on AWS)
    if curl -s -f "http://169.254.169.254/latest/meta-data/instance-id" > /dev/null 2>&1; then
        log_json "DEBUG" "Detected AWS metadata server"
        echo "aws"
        return 0
    fi

    # If no cloud provider detected
    log_json "WARNING" "Could not detect cloud provider environment"
    echo "unknown"
    return 1
}

# Function to validate cloud provider detection
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
    find "$LOG_DIR" -name "node_group_manager_*.log" -type f | sort -r | tail -n +6 | xargs rm -f
    
    # Redirect stdout and stderr to log file and terminal
    exec 1> >(tee -a "$LOG_FILE")
    exec 2>&1
    
    log_json "INFO" "Logging started"
    log_json "INFO" "Log file: $LOG_FILE"
    
    # Log environment information
    log_json "INFO" "Cloud provider: $(detect_cloud_provider)"
    log_json "INFO" "Python version: $(python --version)"
    log_json "INFO" "Working directory: $(pwd)"
}

# Function to run the script with AWS configuration
run_aws() {
    log_json "INFO" "Running with AWS configuration..."
    
    # Validate AWS credentials
    if [ ! -d "/home/appuser/.aws" ]; then
        log_json "ERROR" "AWS credentials not found"
        exit 1
    fi
    
    # Run with retry mechanism
    local max_retries=3
    local retry_count=0
    
    while [ $retry_count -lt $max_retries ]; do
        if python manage_node_groups.py "$@"; then
            log_json "INFO" "Operation completed successfully"
            return 0
        else
            retry_count=$((retry_count + 1))
            log_json "WARNING" "Attempt $retry_count failed, retrying..."
            sleep 5
        fi
    done
    
    log_json "ERROR" "Operation failed after $max_retries attempts"
    return 1
}

# Function to run the script with GCP configuration
run_gcp() {
    log_json "INFO" "Running with GCP configuration..."
    
    # Validate GCP credentials
    if [ ! -d "/home/appuser/.config/gcloud" ]; then
        log_json "ERROR" "GCP credentials not found"
        exit 1
    fi
    
    # Run with retry mechanism
    local max_retries=3
    local retry_count=0
    
    while [ $retry_count -lt $max_retries ]; do
        if python manage_node_groups.py "$@"; then
            log_json "INFO" "Operation completed successfully"
            return 0
        else
            retry_count=$((retry_count + 1))
            log_json "WARNING" "Attempt $retry_count failed, retrying..."
            sleep 5
        fi
    done
    
    log_json "ERROR" "Operation failed after $max_retries attempts"
    return 1
}

# Function to handle errors
handle_error() {
    local exit_code=$?
    log_json "ERROR" "Script failed with exit code $exit_code"
    log_json "ERROR" "Error on line $1"
    exit $exit_code
}

# Set up error handling
trap 'handle_error $LINENO' ERR

# Main execution
main() {
    # Setup logging
    setup_logging
    
    # Detect cloud provider
    CLOUD_PROVIDER=$(detect_cloud_provider)
    
    # Validate cloud provider detection
    if ! validate_cloud_provider "$CLOUD_PROVIDER"; then
        log_json "ERROR" "Cloud provider validation failed"
        exit 1
    fi
    
    log_json "INFO" "Detected cloud provider: $CLOUD_PROVIDER"
    
    # Run based on cloud provider
    case "$CLOUD_PROVIDER" in
        aws)
            run_aws "$@"
            ;;
        gcp)
            run_gcp "$@"
            ;;
        *)
            log_json "ERROR" "Could not determine cloud provider"
            log_json "ERROR" "Please ensure you have the appropriate cloud credentials configured"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@" 