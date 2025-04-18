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
- Build the Docker image
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

## Multi-Architecture Docker Images

The Node Group Manager is available as a multi-architecture Docker image supporting both `amd64` and `arm64` platforms. The images are automatically built and pushed to Docker Hub on every push to the main branch and when tags are created.

### Pulling the Image

```bash
# Pull the latest image
docker pull yourusername/node-group-manager:latest

# Pull a specific version
docker pull yourusername/node-group-manager:v1.0.0
```

### Running on Different Architectures

The image will automatically use the correct architecture for your system:

- **AMD64 (x86_64)**: Standard Intel/AMD processors
- **ARM64**: Apple Silicon (M1/M2) and other ARM-based processors

### Building Locally

To build the multi-arch image locally:

```bash
# Set up Docker Buildx
docker buildx create --use

# Build for both architectures
docker buildx build --platform linux/amd64,linux/arm64 -t yourusername/node-group-manager:latest .

# Push to Docker Hub
docker buildx build --platform linux/amd64,linux/arm64 -t yourusername/node-group-manager:latest --push .
```

### Image Size Optimization

The multi-arch image uses a multi-stage build process to minimize the final image size:
- Base image: ~40MB
- AWS CLI: ~10MB
- GCP SDK: ~100MB
- Application code: ~1MB
- Total size: ~150MB 