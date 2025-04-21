# Node Group Manager

A tool to manage Kubernetes node group scaling for AWS and GCP clusters.

## Quick Start

1. Make sure you have Docker installed
2. Make the setup script executable:
   ```bash
   chmod +x run-container.sh
   ```
3. Run the tool using either command line arguments or environment variables:

### Using Command Line Arguments with Credential Files
```bash
./run-container.sh --cluster-name my-cluster --cloud aws --account 123456789012
```

### Using Environment Variables with Credentials
```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Set tool configuration
export CLUSTER_NAME=my-cluster
export CLOUD_PROVIDER=aws
export ACCOUNT=123456789012
export DRY_RUN=true

# Run the tool
./run-container.sh
```

## Features

- Supports both AWS and GCP cloud providers
- Flexible credential management:
  - Environment variables
  - Credential files
  - Automatic credential detection
- Dry run mode for safe testing
- Flexible tag format parsing
- Automatic role assumption (AWS)
- Operation waiting and validation

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLUSTER_NAME` | Name of the Kubernetes cluster | Yes |
| `CLOUD_PROVIDER` | Cloud provider (aws or gcp) | Yes |
| `ACCOUNT` | AWS account ID or GCP project ID | Yes |
| `REGION` | AWS region (required for AWS) | Yes (AWS only) |
| `DRY_RUN` | Set to 'true' for dry run mode | No |
| `VERBOSE` | Set to 'true' for verbose output | No |

### AWS Credentials

You can provide AWS credentials in two ways:

1. **Environment Variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_SESSION_TOKEN=your_session_token  # Optional
   export AWS_DEFAULT_REGION=us-east-1
   ```

2. **Credential File**:
   Place your credentials in `~/.aws/credentials`:
   ```ini
   [default]
   aws_access_key_id = your_access_key
   aws_secret_access_key = your_secret_key
   region = us-east-1
   ```

### GCP Credentials

You can provide GCP credentials in two ways:

1. **Environment Variable**:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

2. **Credential File**:
   Place your credentials in `~/.config/gcloud/application_default_credentials.json`

## Usage

### AWS Example

```bash
# Using environment variables for credentials
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
export CLUSTER_NAME=my-cluster
export CLOUD_PROVIDER=aws
export ACCOUNT=123456789012
export DRY_RUN=true
./run-container.sh

# Using credential files
./run-container.sh \
  --cluster-name my-cluster \
  --cloud aws \
  --account 123456789012 \
  --region us-east-1 \
  --dry-run
```

### GCP Example

```bash
# Using environment variables for credentials
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
export CLUSTER_NAME=my-cluster
export CLOUD_PROVIDER=gcp
export ACCOUNT=my-project-id
export DRY_RUN=true
./run-container.sh

# Using credential files
./run-container.sh \
  --cluster-name my-cluster \
  --cloud gcp \
  --account my-project-id \
  --dry-run
```

## CI/CD Integration

The tool can be easily integrated into CI/CD pipelines using environment variables:

```yaml
# Example GitHub Actions workflow
jobs:
  manage-node-groups:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Manage Node Groups
        env:
          # Tool configuration
          CLUSTER_NAME: ${{ secrets.CLUSTER_NAME }}
          CLOUD_PROVIDER: ${{ secrets.CLOUD_PROVIDER }}
          ACCOUNT: ${{ secrets.ACCOUNT }}
          REGION: ${{ secrets.REGION }}
          DRY_RUN: false
          
          # AWS credentials
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: ${{ secrets.AWS_DEFAULT_REGION }}
        run: |
          chmod +x run-container.sh
          ./run-container.sh
```

## Security

- The container runs as a non-root user
- Credentials are mounted read-only from the host
- No credentials are stored in the container
- Environment variables are passed securely to the container
- Credential files are mounted read-only

## Troubleshooting

### AWS
- Ensure your AWS credentials are properly configured
- Check that you have the necessary IAM permissions
- Verify the region is correct

### GCP
- Ensure your GCP credentials are properly configured
- Check that you have the necessary IAM permissions
- Verify the project ID is correct

## Support

For detailed error information, check the logs in `/tmp/node_group_manager/`.

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