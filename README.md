# Node Group Manager - Cloud Shell Edition

A tool to manage Kubernetes node groups in AWS and GCP clusters, optimized for cloud shell environments.

## Quick Start

1. Make the script executable:
```bash
chmod +x run-container.sh
```

2. Run the tool:
```bash
./run-container.sh --cluster-name <cluster-name> --cloud <aws|gcp> --account <account-id>
```

The script will automatically:
- Pull the Docker image if not already present
- Detect the cloud provider (or use the one you specify)
- Mount the appropriate credentials
- Run the container with proper logging

## Examples

### AWS Example
```bash
./run-container.sh --cluster-name my-eks-cluster --cloud aws --account 123456789012 --dry-run
```

### GCP Example
```bash
./run-container.sh --cluster-name my-gke-cluster --cloud gcp --account my-gcp-project --dry-run
```

## Logging

All logs are:
- Displayed in real-time in the terminal
- Saved to a log file in `/tmp/node_group_manager_YYYYMMDD_HHMMSS.log`
- Include both stdout and stderr
- Show the cloud provider detection and configuration

## Features

- Automatic cloud provider detection
- Secure credential handling
- Comprehensive logging
- Dry-run mode support
- Verbose output option
- Error handling and reporting

## Security

- Runs as non-root user
- Credentials mounted as read-only
- No sensitive data stored in container
- Temporary credentials used when available

## Troubleshooting

### AWS Issues
- Ensure AWS credentials are configured
- Check IAM permissions
- Verify AWS region settings

### GCP Issues
- Ensure GCP credentials are configured
- Check IAM permissions
- Verify project ID

## Support

For issues or questions, please check the log file in `/tmp` for detailed error information.

## Docker Image

The Node Group Manager is available as a multi-architecture Docker image supporting both `amd64` and `arm64` platforms. The image is automatically built and pushed to Docker Hub on every push to the main branch and when tags are created.

### Image Details
- Repository: `jjjulllesss/wake-up-cloud`
- Architectures: `amd64`, `arm64`
- Size: ~150MB
- Auto-updates: On every main branch push and tag

### Manual Pull

If you want to manually pull the image:
```bash
# Pull the latest version
docker pull jjjulllesss/wake-up-cloud:latest

# Pull a specific version
docker pull jjjulllesss/wake-up-cloud:v1.0.0
```

### Running Manually

You can also run the container directly with Docker:

```bash
# For AWS
docker run -it --rm \
    -v ~/.aws:/home/appuser/.aws:ro \
    -e AWS_DEFAULT_REGION \
    -e AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY \
    -e AWS_SESSION_TOKEN \
    -v /tmp:/tmp \
    jjjulllesss/wake-up-cloud:latest --cluster-name my-cluster --cloud aws --account 123456789012

# For GCP
docker run -it --rm \
    -v ~/.config/gcloud:/home/appuser/.config/gcloud:ro \
    -e GOOGLE_APPLICATION_CREDENTIALS=/home/appuser/.config/gcloud/application_default_credentials.json \
    -v /tmp:/tmp \
    jjjulllesss/wake-up-cloud:latest --cluster-name my-cluster --cloud gcp --account my-project
```

### Image Size Optimization

The multi-arch image uses a multi-stage build process to minimize the final image size:
- Base image: ~40MB
- AWS CLI: ~10MB
- GCP SDK: ~100MB
- Application code: ~1MB
- Total size: ~150MB 