# Node Group Manager

A Python tool to manage Kubernetes node group scaling for AWS and GCP clusters. Scale down clusters to save costs during off-hours and restore them later.

## Features

- **Multi-Cloud Support**: Works with both AWS (EKS) and GCP (GKE) clusters
- **Scale Down Mode**: Scale node groups to 0 and save current state for later restoration
- **Scale Up Mode**: Restore node group scaling from stored tags/labels
- **Dry Run Mode**: Test changes without making actual modifications
- **Flexible Tag Parsing**: Supports multiple tag formats

## Installation

```bash
pip install -r requirements.txt
```

**Dependencies:**
- `boto3>=1.35.0`
- `google-cloud-container>=2.52.0`

## Quick Start

### Scale Down (Save Costs)

```bash
# AWS
python manage_node_groups.py --cluster-name my-cluster --cloud aws --region us-east-1 --scale-down

# GCP
python manage_node_groups.py --cluster-name my-cluster --cloud gcp --account my-project-id --scale-down
```

### Scale Up (Restore)

```bash
# AWS
python manage_node_groups.py --cluster-name my-cluster --cloud aws --region us-east-1

# GCP
python manage_node_groups.py --cluster-name my-cluster --cloud gcp --account my-project-id
```

### Dry Run (Test First)

```bash
python manage_node_groups.py --cluster-name my-cluster --cloud aws --region us-east-1 --scale-down --dry-run
```

## Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--cluster-name` | Yes | Name of the Kubernetes cluster |
| `--cloud` | Yes | Cloud provider: `aws` or `gcp` |
| `--account` | GCP: Yes | AWS account ID or GCP project ID |
| `--region` | AWS: Yes | AWS region (e.g., `us-east-1`) |
| `--scale-down` | No | Scale to 0 and save state |
| `--dry-run` | No | Test without making changes |
| `--verbose`, `-v` | No | Increase verbosity (`-v`, `-vv`) |

## How It Works

### Scale Down Mode
1. Reads current node group configuration (min, max, desired)
2. Saves configuration to tag/label
3. Scales down to 0 nodes

**Tag Names:**
- AWS: `OffHoursPrevious`
- GCP: `offhoursprevious`

### Scale Up Mode (Default)
1. Looks for saved configuration in tags/labels
2. Restores original scaling settings
3. Removes the tag/label

## Tag Format

**AWS:** `MaxSize=X;DesiredCapacity=Y;MinSize=Z`
```
MaxSize=10;DesiredCapacity=5;MinSize=2
```

**GCP:** `maxsizeX-desiredcapacityY-minsizeZ`
```
maxsize10-desiredcapacity5-minsize2
```

## Required Permissions

**AWS:**
- `autoscaling:DescribeAutoScalingGroups`
- `autoscaling:UpdateAutoScalingGroup`
- `autoscaling:CreateOrUpdateTags`
- `autoscaling:DeleteTags`

**GCP:**
- `container.clusters.list`
- `container.clusters.get`
- `container.nodePools.get`
- `container.nodePools.update`
- `container.operations.get`

## Logging

Logs are written to both console and file:
- **Log File**: `/tmp/node_group_manager/node_group_manager.log`
- **Rotation**: 10MB max, 5 backup files

## Common Issues

**No matching resources found:**
- Verify cluster name is correct
- Check AWS region or GCP project ID
- Ensure resources exist and match the cluster name

**Cannot restore (no tag found):**
- Run `--scale-down` first to save state
- Verify tag/label wasn't manually removed

**Authentication errors:**
- AWS: Run `aws configure` or use IAM roles
- GCP: Run `gcloud auth application-default login`

## Important Notes

- ✅ Scales node groups up and down
- ✅ Saves and restores configurations automatically
- ❌ Does NOT manage pod lifecycle
- ❌ Does NOT backup cluster data
- ⚠️ Scaling to 0 terminates all pods on those nodes
- ⚠️ Restore takes 3-5 minutes for instances to launch

## Support

Check logs in `/tmp/node_group_manager/` for detailed error information. Use `-vv` for maximum verbosity.
