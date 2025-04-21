#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default environment variables
CLUSTER_NAME=${CLUSTER_NAME:-}
CLOUD_PROVIDER=${CLOUD_PROVIDER:-}
ACCOUNT=${ACCOUNT:-}
REGION=${REGION:-}
DRY_RUN=${DRY_RUN:-false}
VERBOSE=${VERBOSE:-false}

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to show progress
show_progress() {
    local pid=$1
    local message=$2
    local delay=0.1
    local spinstr='|/-\'
    
    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf "\r[%c] %s" "$spinstr" "$message"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
    done
    printf "\r[✓] %s\n" "$message"
}

# Function to check if running in a cloud shell
is_cloud_shell() {
    if [ -n "$AWS_CLOUD_SHELL" ] || [ -n "$CLOUD_SHELL" ]; then
        return 0
    fi
    return 1
}

# Function to validate credentials
validate_credentials() {
    local cloud_provider=$1
    
    if [ "$cloud_provider" = "aws" ]; then
        # Check for AWS credentials in environment variables
        if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
            print_message "$GREEN" "Using AWS credentials from environment variables"
            if [ -n "$AWS_SESSION_TOKEN" ]; then
                print_message "$GREEN" "Using AWS session token from environment variables"
            fi
            return 0
        fi
        
        # Check for AWS credentials file
        if [ -f ~/.aws/credentials ]; then
            print_message "$GREEN" "Using AWS credentials from ~/.aws/credentials"
            # Check if credentials file contains session token
            if grep -q "aws_session_token" ~/.aws/credentials || grep -q "aws_security_token" ~/.aws/credentials; then
                print_message "$GREEN" "Found AWS session token in credentials file"
            fi
            return 0
        fi
        
        print_message "$RED" "Error: No AWS credentials found"
        print_message "$YELLOW" "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
        print_message "$YELLOW" "Or configure ~/.aws/credentials file"
        print_message "$YELLOW" "Optional: Set AWS_SESSION_TOKEN for temporary credentials"
        return 1
    elif [ "$cloud_provider" = "gcp" ]; then
        # Check for GCP credentials file
        if [ -f ~/.config/gcloud/application_default_credentials.json ]; then
            print_message "$GREEN" "Using GCP credentials from ~/.config/gcloud/application_default_credentials.json"
            # Test credentials using gcloud
            if gcloud auth application-default print-access-token >/dev/null 2>&1; then
                print_message "$GREEN" "GCP credentials validated successfully"
                return 0
            else
                print_message "$RED" "Error: GCP credentials are invalid"
                return 1
            fi
        fi
        
        # Check if running on GCP VM with service account
        if curl -s -f -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token >/dev/null 2>&1; then
            print_message "$GREEN" "Using GCP credentials from VM instance metadata"
            # Test credentials using gcloud
            if gcloud auth list --filter=status:ACTIVE --format="value(account)" >/dev/null 2>&1; then
                print_message "$GREEN" "GCP VM credentials validated successfully"
                return 0
            else
                print_message "$RED" "Error: GCP VM credentials are invalid"
                return 1
            fi
        fi
        
        print_message "$RED" "Error: No GCP credentials found"
        print_message "$YELLOW" "Please configure ~/.config/gcloud/application_default_credentials.json"
        print_message "$YELLOW" "Or run on a GCP VM with service account attached"
        return 1
    fi
    
    return 1
}

# Function to validate input
validate_input() {
    local cloud_provider=$1
    local cluster_name=$2
    local account=$3
    
    if [ -z "$cloud_provider" ]; then
        print_message "$RED" "Error: Cloud provider not specified"
        print_message "$YELLOW" "Set CLOUD_PROVIDER environment variable or use --cloud"
        return 1
    fi
    
    if [ -z "$cluster_name" ]; then
        print_message "$RED" "Error: Cluster name not specified"
        print_message "$YELLOW" "Set CLUSTER_NAME environment variable or use --cluster-name"
        return 1
    fi
    
    # Account is required for GCP, optional for AWS
    if [ "$cloud_provider" = "gcp" ] && [ -z "$account" ]; then
        print_message "$RED" "Error: GCP project ID not specified"
        print_message "$YELLOW" "Set ACCOUNT environment variable or use --account"
        return 1
    fi
    
    if [ "$cloud_provider" != "aws" ] && [ "$cloud_provider" != "gcp" ]; then
        print_message "$RED" "Error: Invalid cloud provider. Must be 'aws' or 'gcp'"
        return 1
    fi
    
    # Validate credentials
    if ! validate_credentials "$cloud_provider"; then
        return 1
    fi
    
    return 0
}

# Function to run the container
run_container() {
    local cloud_provider=$1
    shift

    print_message "$YELLOW" "Running container for $cloud_provider..."
    
    # Build arguments array
    local docker_args=(
        "-it" "--rm"
    )

    # Add environment variables
    if [ -n "$CLUSTER_NAME" ]; then
        docker_args+=("-e" "CLUSTER_NAME=$CLUSTER_NAME")
    fi
    if [ -n "$CLOUD_PROVIDER" ]; then
        docker_args+=("-e" "CLOUD_PROVIDER=$CLOUD_PROVIDER")
    fi
    if [ -n "$ACCOUNT" ]; then
        docker_args+=("-e" "ACCOUNT=$ACCOUNT")
    fi
    if [ -n "$REGION" ]; then
        docker_args+=("-e" "REGION=$REGION")
    fi
    if [ "$DRY_RUN" = "true" ]; then
        docker_args+=("-e" "DRY_RUN=true")
    fi
    if [ "$VERBOSE" = "true" ]; then
        docker_args+=("-e" "VERBOSE=true")
    fi

    # Add AWS-specific environment variables and mounts
    if [ "$cloud_provider" = "aws" ]; then
        # Add AWS environment variables if they exist
        if [ -n "$AWS_ACCESS_KEY_ID" ]; then
            docker_args+=("-e" "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID")
        fi
        if [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
            docker_args+=("-e" "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY")
        fi
        if [ -n "$AWS_SESSION_TOKEN" ]; then
            docker_args+=("-e" "AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN")
        fi
        if [ -n "$AWS_DEFAULT_REGION" ]; then
            docker_args+=("-e" "AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION")
        fi
        
        # Mount AWS credentials directory if it exists
        if [ -d ~/.aws ]; then
            docker_args+=("-v" "$HOME/.aws:/root/.aws:ro")
        fi
    fi

    # Add GCP-specific environment variables and mounts
    if [ "$cloud_provider" = "gcp" ]; then
        # Mount GCP credentials directory if it exists
        if [ -d ~/.config/gcloud ]; then
            docker_args+=("-v" "$HOME/.config/gcloud:/root/.config/gcloud:ro")
        fi
        
        # Add network mode host to access VM metadata
        docker_args+=("--network=host")
    fi

    # Run the container
    docker run "${docker_args[@]}" node-group-manager "$@"
}

# Function to show help
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --cluster-name NAME    Name of the Kubernetes cluster (required)"
    echo "  --cloud PROVIDER       Cloud provider (aws or gcp) (required)"
    echo "  --account ID          AWS account ID or GCP project ID (required for GCP)"
    echo "  --region REGION       AWS region (required for AWS)"
    echo "  --dry-run             Show what would be changed without making changes"
    echo "  --verbose             Increase verbosity"
    echo "  --help                Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  CLUSTER_NAME          Name of the Kubernetes cluster (required)"
    echo "  CLOUD_PROVIDER        Cloud provider (aws or gcp) (required)"
    echo "  ACCOUNT              AWS account ID or GCP project ID (required for GCP)"
    echo "  REGION               AWS region (required for AWS)"
    echo "  DRY_RUN              Set to 'true' for dry run mode"
    echo "  VERBOSE              Set to 'true' for verbose output"
    echo ""
    echo "AWS Credentials:"
    echo "  AWS_ACCESS_KEY_ID     AWS access key ID"
    echo "  AWS_SECRET_ACCESS_KEY AWS secret access key"
    echo "  AWS_SESSION_TOKEN     AWS session token (for temporary credentials)"
    echo "  AWS_DEFAULT_REGION    AWS region"
    echo "  Or use ~/.aws/credentials file"
    echo ""
    echo "GCP Credentials:"
    echo "  Use ~/.config/gcloud/application_default_credentials.json"
    echo "  Or run on a GCP VM with service account attached"
    echo ""
    echo "Examples:"
    echo "  # AWS CloudShell"
    echo "  ./run-container.sh --cluster-name my-cluster --cloud aws --region us-east-1"
    echo ""
    echo "  # GCP CloudShell"
    echo "  ./run-container.sh --cluster-name my-cluster --cloud gcp --account my-project-id"
    echo ""
    echo "  # Local laptop with AWS credentials"
    echo "  export AWS_ACCESS_KEY_ID=your_access_key"
    echo "  export AWS_SECRET_ACCESS_KEY=your_secret_key"
    echo "  export AWS_DEFAULT_REGION=us-east-1"
    echo "  ./run-container.sh --cluster-name my-cluster --cloud aws"
    echo ""
    echo "  # Local laptop with GCP credentials"
    echo "  gcloud auth application-default login"
    echo "  ./run-container.sh --cluster-name my-cluster --cloud gcp --account my-project-id"
    exit 0
}

# Main script
main() {
    # Check if running in cloud shell
    if ! is_cloud_shell; then
        print_message "$YELLOW" "Warning: Not running in a cloud shell environment"
        print_message "$YELLOW" "Some features may not work as expected"
    fi

    # Parse command line arguments
    local args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help)
                show_help
                ;;
            --cluster-name)
                CLUSTER_NAME="$2"
                shift 2
                ;;
            --cloud)
                CLOUD_PROVIDER="$2"
                shift 2
                ;;
            --account)
                ACCOUNT="$2"
                shift 2
                ;;
            --region)
                REGION="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --verbose)
                VERBOSE="true"
                shift
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done

    # Validate input
    if ! validate_input "$CLOUD_PROVIDER" "$CLUSTER_NAME" "$ACCOUNT"; then
        show_help
        exit 1
    fi

    # Run the container
    run_container "$CLOUD_PROVIDER" "${args[@]}"
}

# Execute main function
main "$@" 