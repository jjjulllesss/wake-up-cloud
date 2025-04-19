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

# Function to validate input
validate_input() {
    local cloud_provider=$1
    local cluster_name=$2
    local account=$3
    
    if [ -z "$cloud_provider" ]; then
        print_message "$RED" "Error: Cloud provider not specified"
        return 1
    fi
    
    if [ -z "$cluster_name" ]; then
        print_message "$RED" "Error: Cluster name not specified"
        return 1
    fi
    
    if [ -z "$account" ]; then
        print_message "$RED" "Error: Account ID not specified"
        return 1
    fi
    
    if [ "$cloud_provider" != "aws" ] && [ "$cloud_provider" != "gcp" ]; then
        print_message "$RED" "Error: Invalid cloud provider. Must be 'aws' or 'gcp'"
        return 1
    fi
    
    return 0
}

# Function to ensure image is available
ensure_image() {
    print_message "$YELLOW" "Checking for Docker image..."
    if ! docker image inspect jjjulllesss/wake-up-cloud:latest >/dev/null 2>&1; then
        print_message "$YELLOW" "Pulling Docker image..."
        docker pull jjjulllesss/wake-up-cloud:latest &
        show_progress $! "Pulling Docker image"
    else
        print_message "$GREEN" "Docker image already available"
    fi
}

# Function to run the container
run_container() {
    local cloud_provider=$1
    shift

    print_message "$YELLOW" "Running container for $cloud_provider..."
    
    if [ "$cloud_provider" = "aws" ]; then
        docker run -it --rm \
            -v ~/.aws:/home/appuser/.aws:ro \
            -e AWS_DEFAULT_REGION \
            -e AWS_ACCESS_KEY_ID \
            -e AWS_SECRET_ACCESS_KEY \
            -e AWS_SESSION_TOKEN \
            -v /tmp:/tmp \
            jjjulllesss/wake-up-cloud:latest "$@"
    elif [ "$cloud_provider" = "gcp" ]; then
        docker run -it --rm \
            -v ~/.config/gcloud:/home/appuser/.config/gcloud:ro \
            -e GOOGLE_APPLICATION_CREDENTIALS=/home/appuser/.config/gcloud/application_default_credentials.json \
            -v /tmp:/tmp \
            jjjulllesss/wake-up-cloud:latest "$@"
    else
        print_message "$RED" "Error: Unsupported cloud provider: $cloud_provider"
        exit 1
    fi
}

# Function to show help
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --cloud <aws|gcp>     Cloud provider (required)"
    echo "  --cluster-name <name> Cluster name (required)"
    echo "  --account <id>        AWS account ID or GCP project ID (required)"
    echo "  --dry-run            Show what would be changed without making actual changes"
    echo "  --verbose            Increase verbosity level"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --cloud aws --cluster-name my-cluster --account 123456789012"
    echo "  $0 --cloud gcp --cluster-name my-cluster --account my-project"
}

# Main script
main() {
    # Check if running in cloud shell
    if ! is_cloud_shell; then
        print_message "$YELLOW" "Warning: Not running in a cloud shell environment"
        print_message "$YELLOW" "Some features may not work as expected"
    fi

    # Parse arguments
    local cloud_provider=""
    local cluster_name=""
    local account=""
    local args=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --cloud)
                cloud_provider="$2"
                shift 2
                ;;
            --cluster-name)
                cluster_name="$2"
                shift 2
                ;;
            --account)
                account="$2"
                shift 2
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done

    # Validate input
    if ! validate_input "$cloud_provider" "$cluster_name" "$account"; then
        show_help
        exit 1
    fi

    # If cloud provider not specified, try to detect it
    if [ -z "$cloud_provider" ]; then
        if [ -n "$AWS_CLOUD_SHELL" ] || [ -n "$AWS_ACCESS_KEY_ID" ]; then
            cloud_provider="aws"
        elif [ -n "$CLOUD_SHELL" ] || [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
            cloud_provider="gcp"
        else
            print_message "$RED" "Error: Could not determine cloud provider"
            print_message "$RED" "Please specify --cloud aws or --cloud gcp"
            exit 1
        fi
    fi

    # Ensure image is available
    ensure_image

    # Run the container
    run_container "$cloud_provider" "${args[@]}"
}

# Execute main function
main "$@" 