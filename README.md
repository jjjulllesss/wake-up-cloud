# Node Group Manager

A Python tool to manage Kubernetes node group scaling for AWS and GCP clusters. This script handles both AWS Auto Scaling Groups and GCP Node Pools, allowing you to restore previous scaling configurations based on tags/labels.

## Features

- **Multi-Cloud Support**: Works with both AWS (EKS) and GCP (GKE) clusters
- **Automatic Scaling Restoration**: Restores node group scaling parameters from stored tags/labels
- **Dry Run Mode**: Test changes without making actual modifications
- **Flexible Tag Parsing**: Supports multiple tag formats for different cloud providers
- **Comprehensive Logging**: Detailed logging to both console and rotating log files
- **Error Handling**: Robust error handling with detailed error messages
- **Operation Validation**: Validates scaling parameters before applying changes

## Prerequisites

- Python 3.7 or higher
- AWS CLI configured with appropriate credentials (for AWS)
- GCP credentials configured (for GCP)
- Required permissions to manage Auto Scaling Groups (AWS) or Node Pools (GCP)

### AWS Permissions Required

- `autoscaling:DescribeAutoScalingGroups`
- `autoscaling:UpdateAutoScalingGroup`
- `autoscaling:DeleteTags`
- `ec2:DescribeInstances` (for some operations)

### GCP Permissions Required

- `container.clusters.get`
- `container.clusters.list`
- `container.nodePools.get`
- `container.nodePools.update`
- `container.operations.get`

## Installation

### Quick Install (One-Line)

Download the script, install dependencies, and get started with a single command:

```bash
curl -sSL https://raw.githubusercontent.com/jjjulllesss/wake-up-cloud/main/manage_node_groups.py -o manage_node_groups.py && curl -sSL https://raw.githubusercontent.com/jjjulllesss/wake-up-cloud/main/requirements.txt -o requirements.txt && pip3 install -q -r requirements.txt && chmod +x manage_node_groups.py && echo '✅ Installation complete!' && python3 manage_node_groups.py --help
```

### Manual Installation

1. Clone or download this repository

2. Install dependencies:

```bash
pip install -r requirements.txt
```

Or using a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python manage_node_groups.py --cluster-name <cluster-name> --cloud <aws|gcp> [options]
```

### AWS Example

```bash
python manage_node_groups.py \
  --cluster-name my-eks-cluster \
  --cloud aws \
  --region us-east-1 \
  --account 123456789012
```

### GCP Example

```bash
python manage_node_groups.py \
  --cluster-name my-gke-cluster \
  --cloud gcp \
  --account my-gcp-project-id
```

### Dry Run Mode

Test changes without making actual modifications:

```bash
python manage_node_groups.py \
  --cluster-name my-cluster \
  --cloud aws \
  --region us-east-1 \
  --dry-run
```

### Verbose Logging

Increase logging verbosity:

```bash
python manage_node_groups.py \
  --cluster-name my-cluster \
  --cloud aws \
  --region us-east-1 \
  -v      # INFO level
  -vv     # DEBUG level
```

## Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--cluster-name` | Yes | Name of the Kubernetes cluster to manage |
| `--cloud` | Yes | Cloud provider: `aws` or `gcp` |
| `--account` | GCP: Yes<br>AWS: Optional | AWS account ID or GCP project ID |
| `--region` | AWS: Yes<br>GCP: No | AWS region (e.g., `us-east-1`) |
| `--dry-run` | No | Show what would be changed without making changes |
| `--verbose`, `-v` | No | Increase verbosity (can be used multiple times) |

## Tag Format

The script uses tags/labels to store and restore scaling configurations. The tag name differs by cloud provider:

- **AWS**: `OffHoursPrevious`
- **GCP**: `offhoursprevious`

### AWS Tag Format

```
MaxSize=X;DesiredCapacity=Y;MinSize=Z
```

Example:
```
MaxSize=10;DesiredCapacity=5;MinSize=2
```

### GCP Tag Format

```
maxsizeX-desiredcapacityY-minsizeZ
```

Example:
```
maxsize10-desiredcapacity5-minsize2
```

### Tag Value Validation

- All values must be non-negative integers
- Maximum size cannot exceed 1000
- Minimum size must be ≤ maximum size
- Desired capacity must be between minimum and maximum size

## How It Works

### AWS (Auto Scaling Groups)

1. The script searches for all Auto Scaling Groups in the specified region
2. Filters ASGs matching the cluster name
3. Looks for the `OffHoursPrevious` tag on each ASG
4. Parses the tag value to extract scaling parameters
5. Updates the ASG with the restored scaling parameters:
   - `MinSize`
   - `MaxSize`
   - `DesiredCapacity`
6. Removes the `OffHoursPrevious` tag after successful update

### GCP (Node Pools)

1. The script connects to the GKE API
2. Lists all clusters in the project
3. Finds the cluster matching the specified name
4. For each node pool in the cluster:
   - Checks for the `offhoursprevious` label
   - Parses the label value to extract scaling parameters
   - Updates the node pool with the restored configuration:
     - Sets node count to desired capacity
     - Enables autoscaling with min/max limits
     - Removes the `offhoursprevious` label after processing

## Logging

The script logs to both console and file:

- **Console**: Real-time output with timestamps
- **File**: Rotating log files in `/tmp/node_group_manager/node_group_manager.log`
  - Maximum file size: 10MB
  - Backup count: 5 files
  - Automatic rotation when size limit is reached

## Error Handling

The script includes comprehensive error handling:

- **Validation Errors**: Invalid input parameters are caught and reported
- **API Errors**: AWS/GCP API errors are logged with details
- **Parsing Errors**: Invalid tag formats are reported with expected format examples
- **Timeout Errors**: GCP operations have a default 600-second timeout

## Examples

### Restore Scaling for AWS Cluster

```bash
python manage_node_groups.py \
  --cluster-name production-eks \
  --cloud aws \
  --region us-west-2 \
  --account 123456789012
```

### Test GCP Scaling Changes

```bash
python manage_node_groups.py \
  --cluster-name staging-gke \
  --cloud gcp \
  --account my-project-id \
  --dry-run \
  -vv
```

## Troubleshooting

### No ASGs Found Matching Cluster Name

- Verify the cluster name is correct
- Check that ASGs exist in the specified region
- Ensure ASG names contain the cluster name as a substring

### Tag Parsing Errors

- Verify tag format matches the expected format for your cloud provider
- Check that all three values (min, max, desired) are present
- Ensure values are valid integers within acceptable ranges

### Authentication Errors

**AWS:**
- Ensure AWS credentials are configured (`aws configure`)
- Verify IAM permissions are sufficient
- Check if using temporary credentials (CloudShell, etc.)

**GCP:**
- Ensure GCP credentials are configured (`gcloud auth application-default login`)
- Verify service account has necessary permissions
- Check project ID is correct

### GCP Operation Timeouts

- Increase timeout if operations take longer than 10 minutes
- Check GCP console for any ongoing operations that might conflict
- Verify network connectivity to GCP APIs

## Development

### Running Tests

(Add test instructions if tests are added in the future)

### Code Structure

- `NodeGroupManager`: Main class handling cloud-agnostic operations
- `ScalingOperation`: Dataclass representing a scaling operation
- `CloudProvider`: Enum for supported cloud providers
- `_manage_aws_node_groups()`: AWS-specific implementation
- `_manage_gcp_node_groups()`: GCP-specific implementation

## License

(Add license information if applicable)

## Contributing

(Add contribution guidelines if applicable)

## Support

For issues or questions, please check the logs in `/tmp/node_group_manager/` for detailed error information.

