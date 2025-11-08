#!/usr/bin/env python3

"""
Node Group Manager
-----------------
A tool to manage Kubernetes node group scaling for AWS and GCP clusters.
This script handles both AWS Auto Scaling Groups and GCP Node Pools.

Usage:
    python manage_node_groups.py --cluster-name <name> --cloud <aws|gcp> --account <id>

Features:
    - Supports both AWS and GCP cloud providers
    - Dry run mode for safe testing
    - Flexible tag format parsing
    - Automatic role assumption (AWS)
    - Operation waiting and validation
"""

import argparse
import logging
import sys
import time
import re
import os
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler

import boto3
from botocore.exceptions import ClientError
from google.cloud import container_v1
from google.api_core import exceptions as google_exceptions

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create log directory if it doesn't exist (cross-platform)
log_dir = os.path.join(tempfile.gettempdir(), "node_group_manager")
os.makedirs(log_dir, exist_ok=True)

# Set up file handler with rotation
log_file = os.path.join(log_dir, "node_group_manager.log")
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

# Set up console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Log startup information
logger.info("Starting Node Group Manager")
logger.info("Log file: %s", log_file)
logger.info("Python version: %s", sys.version)
logger.info("Working directory: %s", os.getcwd())

class CloudProvider(Enum):
    """Supported cloud providers."""
    AWS = 'aws'
    GCP = 'gcp'

@dataclass
class ScalingOperation:
    """Represents a node group scaling operation.
    
    Attributes:
        resource_name: Name of the node group/ASG
        current_size: Current number of nodes
        target_size: Desired number of nodes
        min_size: Minimum number of nodes
        max_size: Maximum number of nodes
        provider: Cloud provider (AWS or GCP)
    """
    resource_name: str
    current_size: int
    target_size: int
    min_size: int
    max_size: int
    provider: CloudProvider

class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass

class NodeGroupManager:
    """Main class for managing node groups across cloud providers."""
    
    def __init__(self, cluster_name: str, cloud_provider: str, account: str = None, region: str = None, dry_run: bool = False):
        """Initialize the node group manager.
        
        Args:
            cluster_name: Name of the Kubernetes cluster
            cloud_provider: Cloud provider ('aws' or 'gcp')
            account: AWS account ID or GCP project ID (required for GCP)
            region: AWS region (required for AWS)
            dry_run: If True, only show what would be changed
        """
        logger.info("Initializing NodeGroupManager")
        logger.info("Cluster name: %s", cluster_name)
        logger.info("Cloud provider: %s", cloud_provider)
        logger.info("Account: %s", account)
        logger.info("Region: %s", region)
        logger.info("Dry run mode: %s", dry_run)
        
        self.cluster_name = cluster_name
        self.cloud_provider = CloudProvider(cloud_provider.lower())
        self.account = account
        self.region = region
        self.dry_run = dry_run
        self.operations: List[ScalingOperation] = []
        
        logger.info("Validating inputs...")
        self.validate_inputs()
        logger.info("Input validation completed successfully")

    @property
    def tag_name(self) -> str:
        """Get the appropriate tag name based on cloud provider.
        
        Returns:
            str: Tag name for the current cloud provider
        """
        return "OffHoursPrevious" if self.cloud_provider == CloudProvider.AWS else "offhoursprevious"

    def validate_inputs(self) -> None:
        """Validate input parameters.
        
        Raises:
            ValidationError: If any input is invalid
        """
        if not self.cluster_name:
            raise ValidationError("Cluster name cannot be empty")
        
        if self.cloud_provider == CloudProvider.GCP and not self.account:
            raise ValidationError("GCP project ID is required")
        
        if self.cloud_provider == CloudProvider.AWS and not self.region:
            raise ValidationError("AWS region is required")

    def manage_node_groups(self) -> None:
        """Main method to manage node groups.
        
        This method delegates to the appropriate cloud provider's implementation.
        
        Raises:
            Exception: If any error occurs during management
        """
        try:
            if self.cloud_provider == CloudProvider.AWS:
                self._manage_aws_node_groups()
            else:
                self._manage_gcp_node_groups()
        except Exception as e:
            logger.error(f"Error managing node groups: {str(e)}")
            raise

    def _parse_scaling_values(self, tag_value: str) -> Tuple[int, int, int]:
        """Parse scaling values from a tag.
        
        Supports multiple formats:
        - AWS: MaxSize=X;DesiredCapacity=Y;MinSize=Z
        - GCP: maxsizeX-desiredcapacityY-minsizeZ
        - Legacy: maxsizeX-minsizeY-desiredsizeZ
        
        Args:
            tag_value: The tag value to parse
            
        Returns:
            Tuple of (max_size, desired_capacity, min_size)
            
        Raises:
            ValueError: If parsing fails or values are invalid
        """
        try:
            normalized_value = tag_value.lower()
            logger.debug(f"Parsing tag: {tag_value}")
            
            # Parse AWS format (semicolon-separated)
            if ';' in normalized_value:
                values = self._parse_aws_format(normalized_value)
            
            # Parse GCP format (dash-separated)
            elif '-' in normalized_value:
                values = self._parse_gcp_format(normalized_value)
            
            else:
                raise ValueError("Unsupported tag format")
            
            # Validate parsed values
            self._validate_scaling_values(values)
            return values['max'], values['desired'], values['min']
                
        except Exception as e:
            logger.error(f"Error parsing tag: {tag_value}")
            raise ValueError(
                "Invalid tag format. Expected:\n"
                "AWS: MaxSize=X;DesiredCapacity=Y;MinSize=Z\n"
                "GCP: maxsizeX-desiredcapacityY-minsizeZ\n"
                f"Got: {tag_value}"
            )

    def _parse_aws_format(self, value: str) -> Dict[str, int]:
        """Parse AWS format tag value.
        
        Handles random order of parameters in the tag value.
        Looks for keys containing 'maxsize', 'minsize', or 'desiredcapacity'
        regardless of their position in the string.
        """
        values = {}
        for param in value.split(';'):
            param = param.strip()
            if not param:
                continue
            try:
                key, val = param.split('=', 1)
                key = key.strip().lower()
                val = val.strip()
                
                # Match keys regardless of order - look for specific patterns
                if 'maxsize' in key or (key.startswith('max') and 'size' in key):
                    values['max'] = int(val)
                elif 'minsize' in key or (key.startswith('min') and 'size' in key):
                    values['min'] = int(val)
                elif 'desiredcapacity' in key or ('desired' in key and 'capacity' in key):
                    values['desired'] = int(val)
                else:
                    logger.warning(f"Unrecognized key in AWS tag format: {key}")
            except ValueError as e:
                logger.warning(f"Error parsing parameter '{param}': {str(e)}")
                continue
        
        if len(values) != 3:
            missing = []
            if 'max' not in values:
                missing.append('MaxSize')
            if 'min' not in values:
                missing.append('MinSize')
            if 'desired' not in values:
                missing.append('DesiredCapacity')
            raise ValueError(f"Missing required values in AWS format: {', '.join(missing)}")
        return values

    def _parse_gcp_format(self, value: str) -> Dict[str, int]:
        """Parse GCP format tag value."""
        values = {}
        for part in value.split('-'):
            part = part.strip()
            if 'max' in part:
                values['max'] = int(''.join(filter(str.isdigit, part)))
            elif 'min' in part:
                values['min'] = int(''.join(filter(str.isdigit, part)))
            elif 'desired' in part:
                values['desired'] = int(''.join(filter(str.isdigit, part)))
        
        if len(values) != 3:
            raise ValueError("Missing required values in GCP format")
        return values

    def _validate_scaling_values(self, values: Dict[str, int]) -> None:
        """Validate scaling values.
        
        Args:
            values: Dictionary containing max, min, and desired values
            
        Raises:
            ValueError: If values are invalid
        """
        max_size = values['max']
        min_size = values['min']
        desired = values['desired']
        
        if any(v < 0 for v in values.values()):
            raise ValueError("Values must be non-negative")
        
        if max_size > 1000:
            raise ValueError(f"Max size {max_size} exceeds limit of 1000")
        
        if min_size > max_size:
            raise ValueError(f"Min size {min_size} > max size {max_size}")
        
        if not min_size <= desired <= max_size:
            raise ValueError(f"Desired {desired} not between min {min_size} and max {max_size}")

    def _get_aws_client(self, service_name: str):
        """Get an AWS client for the specified service.
        
        Args:
            service_name: Name of the AWS service
            
        Returns:
            boto3.client: AWS client for the specified service
            
        Raises:
            Exception: If client creation fails
        """
        logger.info("Creating AWS client for service: %s", service_name)
        try:
            # Create a session to use the default credential provider chain
            session = boto3.Session()
            
            # Log which credential source is being used
            credentials = session.get_credentials()
            if credentials.token:
                logger.info("Using AWS session credentials (likely from CloudShell)")
            elif credentials.access_key:
                logger.info("Using AWS access key credentials")
            else:
                logger.info("Using default AWS credential provider chain")
            
            # Create client with the session
            return session.client(service_name, region_name=self.region)
        except Exception as e:
            logger.error(f"Failed to create AWS {service_name} client: {str(e)}")
            raise

    def _add_operation(self, operation: ScalingOperation) -> None:
        """Add a scaling operation to the planned operations list.
        
        This method adds a scaling operation to the list of operations to be performed.
        In dry run mode, it only logs the operation without executing it.
        
        Args:
            operation: The scaling operation to add
        """
        self.operations.append(operation)
        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Planning to scale {operation.resource_name} "
            f"from {operation.current_size} to {operation.target_size} nodes "
            f"(min={operation.min_size}, max={operation.max_size})"
        )

    def _execute_operations(self) -> None:
        """Execute all planned scaling operations.
        
        This method executes all operations that were added to the operations list.
        In dry run mode, it only logs the operations without making any changes.
        """
        if self.dry_run:
            logger.info("Dry run completed. No changes were made.")
            return

        for operation in self.operations:
            logger.info(f"Executing scaling operation for {operation.resource_name}")
            # Implementation of actual scaling operations...

    def _manage_aws_node_groups(self) -> None:
        """Manage AWS Auto Scaling Groups for the specified cluster.
        
        This method:
        1. Finds all ASGs matching the cluster name
        2. Checks for OffHoursPrevious tags
        3. Updates scaling parameters based on tag values
        
        Raises:
            ClientError: If AWS API calls fail
            ValueError: If tag parsing fails
        """
        try:
            logger.info(f"Starting AWS node group management for cluster: {self.cluster_name}")
            logger.info(f"Using AWS region: {self.region}")
            
            # Get AWS clients
            autoscaling = self._get_aws_client('autoscaling')
            ec2 = self._get_aws_client('ec2')
            
            # Get all ASGs
            logger.info("Fetching Auto Scaling Groups...")
            paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
            asg_count = 0
            matching_asg_count = 0
            
            for page in paginator.paginate():
                for asg in page['AutoScalingGroups']:
                    asg_count += 1
                    asg_name = asg['AutoScalingGroupName']
                    logger.debug(f"Found ASG: {asg_name}")
                    
                    # Check if ASG name contains cluster name
                    if self.cluster_name in asg_name:
                        matching_asg_count += 1
                        logger.info(f"Found matching ASG: {asg_name}")
                        try:
                            off_hours_previous = None
                            
                            # Find OffHoursPrevious tag
                            for tag in asg['Tags']:
                                if tag['Key'] == self.tag_name:
                                    off_hours_previous = tag['Value']
                                    logger.info(f"Found {self.tag_name} tag with value: {off_hours_previous}")
                                    break
                            
                            if off_hours_previous:
                                try:
                                    max_size, desired_capacity, min_size = self._parse_scaling_values(off_hours_previous)
                                    
                                    # Add operation to the list
                                    operation = ScalingOperation(
                                        resource_name=asg_name,
                                        current_size=asg['DesiredCapacity'],
                                        target_size=desired_capacity,
                                        min_size=min_size,
                                        max_size=max_size,
                                        provider=CloudProvider.AWS
                                    )
                                    self._add_operation(operation)
                                    
                                    # Execute operation if not in dry run mode
                                    if not self.dry_run:
                                        logger.info(f"Updating scaling parameters for ASG: {asg_name}")
                                        autoscaling.update_auto_scaling_group(
                                            AutoScalingGroupName=asg_name,
                                            MinSize=min_size,
                                            MaxSize=max_size,
                                            DesiredCapacity=desired_capacity
                                        )
                                        logger.info(f"Successfully updated scaling parameters for {asg_name}")
                                        
                                        # Remove the OffHoursPrevious tag after successful update
                                        logger.info(f"Removing {self.tag_name} tag from ASG: {asg_name}")
                                        autoscaling.delete_tags(
                                            Tags=[
                                                {
                                                    'ResourceId': asg_name,
                                                    'ResourceType': 'auto-scaling-group',
                                                    'Key': self.tag_name
                                                }
                                            ]
                                        )
                                        logger.info(f"Successfully removed {self.tag_name} tag from {asg_name}")
                                    
                                except ValueError as e:
                                    logger.error(f"Error parsing scaling values for ASG {asg_name}: {str(e)}")
                                    continue
                            else:
                                logger.info(f"No {self.tag_name} tag found for ASG: {asg_name}")
                            
                        except ClientError as e:
                            logger.error(f"Error processing ASG {asg_name}: {str(e)}")
                    else:
                        logger.debug(f"Skipping non-matching ASG: {asg_name}")
            
            logger.info(f"Processed {asg_count} total ASGs")
            logger.info(f"Found {matching_asg_count} ASGs matching cluster name: {self.cluster_name}")
            if matching_asg_count == 0:
                logger.warning(f"No ASGs found matching cluster name: {self.cluster_name}")
                        
        except ClientError as e:
            logger.error(f"AWS API error: {str(e)}")
            raise

    def _wait_for_operation(self, client: container_v1.ClusterManagerClient, project_id: str, location: str, operation_name: str, timeout_seconds: int = 600) -> None:
        """Wait for a GKE operation to complete.
        
        This method polls the GKE API to check the status of an operation.
        It will wait until the operation completes, fails, or times out.
        
        Args:
            client: The GKE ClusterManagerClient
            project_id: The GCP project ID
            location: The location of the operation
            operation_name: The name of the operation
            timeout_seconds: Maximum time to wait (default: 600)
            
        Raises:
            TimeoutError: If the operation times out
            Exception: If the operation fails
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            operation_request = container_v1.types.GetOperationRequest(
                name=f"projects/{project_id}/locations/{location}/operations/{operation_name}"
            )
            operation_response = client.get_operation(request=operation_request)
            
            if operation_response.status == container_v1.Operation.Status.DONE:
                logger.info("Operation completed successfully.")
                return
            elif operation_response.status == container_v1.Operation.Status.RUNNING:
                logger.info("Operation is still running...")
                time.sleep(5)
            elif operation_response.status == container_v1.Operation.Status.ABORTING:
                logger.warning("Operation is aborting.")
                return
            else:
                logger.error(f"Unexpected operation status: {operation_response.status}")
                time.sleep(5)

        raise TimeoutError(f"Operation {operation_name} timed out after {timeout_seconds} seconds.")

    def _manage_gcp_node_groups(self) -> None:
        """Manage GCP node pools for the specified cluster.
        
        This method:
        1. Connects to the GKE API
        2. Finds the specified cluster
        3. Updates node pool configurations
        4. Handles scaling operations
        
        Raises:
            google_exceptions.GoogleAPIError: If GCP API calls fail
            ValueError: If tag parsing fails
        """
        try:
            client = container_v1.ClusterManagerClient()
            project_id = self.account
            parent = f"projects/{project_id}/locations/-"
            
            try:
                clusters = client.list_clusters(parent=parent)
                
                for cluster in clusters.clusters:
                    if cluster.name == self.cluster_name:
                        for node_pool in cluster.node_pools:
                            try:
                                self._process_gcp_node_pool(client, project_id, cluster, node_pool)
                            except google_exceptions.GoogleAPIError as e:
                                logger.error(f"Error processing node pool {node_pool.name}: {str(e)}")
                                
            except google_exceptions.GoogleAPIError as e:
                logger.error(f"Error listing clusters: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"GCP API error: {str(e)}")
            raise

    def _process_gcp_node_pool(self, client: container_v1.ClusterManagerClient, project_id: str, cluster: Any, node_pool: Any) -> None:
        """Process a single GCP node pool.
        
        Args:
            client: The GKE ClusterManagerClient
            project_id: The GCP project ID
            cluster: The GKE cluster
            node_pool: The node pool to process
        """
        node_pool_name = f"projects/{project_id}/locations/{cluster.location}/clusters/{cluster.name}/nodePools/{node_pool.name}"
        node_pool_details = client.get_node_pool(name=node_pool_name)
        
        # Store current configuration
        current_labels = dict(node_pool_details.config.labels)
        current_labels[self.tag_name] = (
            f"maxsize{node_pool.autoscaling.max_node_count}-"
            f"desiredcapacity{node_pool.initial_node_count}-"
            f"minsize{node_pool.autoscaling.min_node_count}"
        )
        
        # Update labels if not in dry run mode
        if not self.dry_run:
            update_request = container_v1.UpdateNodePoolRequest(
                name=node_pool_name,
                labels=container_v1.NodeLabels(labels=current_labels)
            )
            operation = client.update_node_pool(request=update_request)
            logger.info(f"Storing current configuration for node pool {node_pool.name}")
            self._wait_for_operation(client, project_id, cluster.location, operation.name.split('/')[-1])
        
        # Check for offhoursprevious in labels
        if self.tag_name in node_pool_details.config.labels:
            off_hours_previous = node_pool_details.config.labels[self.tag_name]
            logger.info(f"Found {self.tag_name} tag for node pool: {node_pool.name}")
            
            try:
                max_size, desired_capacity, min_size = self._parse_scaling_values(off_hours_previous)
                
                # Add operation to the list
                operation = ScalingOperation(
                    resource_name=node_pool.name,
                    current_size=node_pool.initial_node_count,
                    target_size=desired_capacity,
                    min_size=min_size,
                    max_size=max_size,
                    provider=CloudProvider.GCP
                )
                self._add_operation(operation)
                
                # Execute operation if not in dry run mode
                if not self.dry_run:
                    self._execute_gcp_scaling(client, node_pool_name, project_id, cluster.location, 
                                           desired_capacity, min_size, max_size, current_labels)
                    
            except ValueError as e:
                logger.error(f"Error parsing scaling values for node pool {node_pool.name}: {str(e)}")
            except google_exceptions.GoogleAPIError as e:
                logger.error(f"Error updating node pool {node_pool.name}: {str(e)}")

    def _execute_gcp_scaling(self, client: container_v1.ClusterManagerClient, node_pool_name: str, 
                           project_id: str, location: str, desired_capacity: int, 
                           min_size: int, max_size: int, current_labels: Dict[str, str]) -> None:
        """Execute GCP node pool scaling operations.
        
        Args:
            client: The GKE ClusterManagerClient
            node_pool_name: Full name of the node pool
            project_id: The GCP project ID
            location: The cluster location
            desired_capacity: Target number of nodes
            min_size: Minimum number of nodes
            max_size: Maximum number of nodes
            current_labels: Current node pool labels
        """
        # Set node pool size
        size_request = container_v1.SetNodePoolSizeRequest(
            name=node_pool_name,
            node_count=desired_capacity
        )
        operation = client.set_node_pool_size(request=size_request)
        logger.info(f"Setting node pool size to {desired_capacity}")
        self._wait_for_operation(client, project_id, location, operation.name.split('/')[-1])
        
        # Enable autoscaling
        autoscaling_request = container_v1.SetNodePoolAutoscalingRequest(
            name=node_pool_name,
            autoscaling=container_v1.NodePoolAutoscaling(
                enabled=True,
                min_node_count=min_size,
                max_node_count=max_size
            )
        )
        operation = client.set_node_pool_autoscaling(request=autoscaling_request)
        logger.info("Enabling autoscaling")
        self._wait_for_operation(client, project_id, location, operation.name.split('/')[-1])
        
        # Remove the offhoursprevious label
        current_labels.pop(self.tag_name, None)
        update_request = container_v1.UpdateNodePoolRequest(
            name=node_pool_name,
            labels=container_v1.NodeLabels(labels=current_labels)
        )
        operation = client.update_node_pool(request=update_request)
        logger.info(f"Removing {self.tag_name} label")
        self._wait_for_operation(client, project_id, location, operation.name.split('/')[-1])

def main():
    """Main entry point for the script.
    
    This function:
    1. Parses command line arguments
    2. Configures logging
    3. Creates and runs the NodeGroupManager
    4. Handles errors and exits appropriately
    """
    parser = argparse.ArgumentParser(
        prog='python3 manage_node_groups.py',
        description='Manage Kubernetes node groups scaling for AWS and GCP clusters',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Required arguments
    parser.add_argument(
        '--cluster-name',
        required=True,
        help='Name of the Kubernetes cluster to manage (REQUIRED)'
    )
    parser.add_argument(
        '--cloud',
        required=True,
        choices=['aws', 'gcp'],
        help='Cloud provider: aws or gcp (REQUIRED)'
    )
    parser.add_argument(
        '--account',
        help='AWS account ID or GCP project ID (REQUIRED for GCP)'
    )
    
    # Optional arguments
    parser.add_argument(
        '--region',
        help='AWS region (REQUIRED for AWS)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making actual changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='count',
        default=0,
        help='Increase verbosity (can be used multiple times)'
    )
    
    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.verbose == 1:
        logger.setLevel(logging.INFO)
    elif args.verbose >= 2:
        logger.setLevel(logging.DEBUG)
    
    try:
        manager = NodeGroupManager(
            cluster_name=args.cluster_name,
            cloud_provider=args.cloud,
            account=args.account,
            region=args.region,
            dry_run=args.dry_run
        )
        manager.manage_node_groups()
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Script execution failed: {str(e)}")
        if args.verbose >= 2:
            logger.exception("Detailed error information:")
        sys.exit(1)

if __name__ == '__main__':
    main() 