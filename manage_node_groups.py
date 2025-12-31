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
import os
import tempfile
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError
from google.cloud import container_v1
from google.cloud import compute_v1
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

# Log startup information (detailed info goes to file, minimal to console)
logger.debug("Starting Node Group Manager")
logger.debug("Log file: %s", log_file)
logger.debug("Python version: %s", sys.version)
logger.debug("Working directory: %s", os.getcwd())

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
    
    def __init__(self, cluster_name: str, cloud_provider: str, account: str = None, region: str = None, dry_run: bool = False, scale_down: bool = False):
        """Initialize the node group manager.
        
        Args:
            cluster_name: Name of the Kubernetes cluster
            cloud_provider: Cloud provider ('aws' or 'gcp')
            account: AWS account ID or GCP project ID (required for GCP)
            region: AWS region (required for AWS)
            dry_run: If True, only show what would be changed
            scale_down: If True, scale down to 0 and save current state
        """
        self.cluster_name = cluster_name
        self.cloud_provider = CloudProvider(cloud_provider.lower())
        self.account = account
        self.region = region
        self.dry_run = dry_run
        self.scale_down = scale_down
        self.operations: List[ScalingOperation] = []
        
        # Log configuration (detailed to file, summary to console)
        logger.debug("Initializing NodeGroupManager")
        logger.debug("Cluster name: %s", cluster_name)
        logger.debug("Cloud provider: %s", cloud_provider)
        logger.debug("Account: %s", account)
        logger.debug("Region: %s", region)
        logger.debug("Dry run mode: %s", dry_run)
        logger.debug("Scale down mode: %s", scale_down)
        
        logger.info(f"Managing node groups for cluster: {cluster_name} ({cloud_provider.upper()})")
        if self.region:
            logger.info(f"Region: {region}")
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        if self.scale_down:
            logger.info("SCALE DOWN MODE - Will scale to 0 and save current state")
        
        logger.debug("Validating inputs...")
        self.validate_inputs()
        logger.debug("Input validation completed successfully")

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
        logger.debug("Creating AWS client for service: %s", service_name)
        try:
            # Create a session to use the default credential provider chain
            session = boto3.Session()
            
            # Log which credential source is being used (only once, on first client creation)
            if not hasattr(self, '_aws_credentials_logged'):
                credentials = session.get_credentials()
                if credentials.token:
                    logger.debug("Using AWS session credentials (likely from CloudShell)")
                elif credentials.access_key:
                    logger.debug("Using AWS access key credentials")
                else:
                    logger.debug("Using default AWS credential provider chain")
                self._aws_credentials_logged = True
            
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
        if self.dry_run:
            if self.scale_down and operation.target_size == 0:
                logger.info(
                    f"[DRY RUN] Would scale down {operation.resource_name} "
                    f"from {operation.current_size} to 0 nodes "
                    f"and save state (min={operation.min_size}, max={operation.max_size}, desired={operation.current_size})"
                )
            else:
                logger.info(
                    f"[DRY RUN] Would scale {operation.resource_name} "
                    f"from {operation.current_size} to {operation.target_size} nodes "
                    f"(min={operation.min_size}, max={operation.max_size})"
                )
        else:
            logger.debug(
                f"Planning to scale {operation.resource_name} "
                f"from {operation.current_size} to {operation.target_size} nodes "
                f"(min={operation.min_size}, max={operation.max_size})"
            )

    def _process_aws_asg(self, asg: Dict) -> bool:
        """Process a single AWS ASG (scale down or scale up).
        
        Args:
            asg: ASG dictionary from describe_auto_scaling_groups
            
        Returns:
            bool: True if the ASG was processed, False otherwise
        """
        asg_name = asg['AutoScalingGroupName']
        autoscaling = self._get_aws_client('autoscaling')
        
        try:
            if self.scale_down:
                # Scale down mode: save current state and scale to 0
                return self._scale_down_aws_asg(autoscaling, asg, asg_name)
            else:
                # Scale up mode: restore from OffHoursPrevious tag
                off_hours_previous = None
                
                # Find OffHoursPrevious tag
                for tag in asg['Tags']:
                    if tag['Key'] == self.tag_name:
                        off_hours_previous = tag['Value']
                        logger.debug(f"Found {self.tag_name} tag with value: {off_hours_previous}")
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
                            logger.info(f"  → Updating {asg_name}: scaling from {asg['DesiredCapacity']} to {desired_capacity} nodes (min={min_size}, max={max_size})")
                            autoscaling.update_auto_scaling_group(
                                AutoScalingGroupName=asg_name,
                                MinSize=min_size,
                                MaxSize=max_size,
                                DesiredCapacity=desired_capacity
                            )
                            logger.info(f"  ✓ Successfully updated {asg_name}")
                            
                            # Remove the OffHoursPrevious tag after successful update
                            autoscaling.delete_tags(
                                Tags=[
                                    {
                                        'ResourceId': asg_name,
                                        'ResourceType': 'auto-scaling-group',
                                        'Key': self.tag_name
                                    }
                                ]
                            )
                            logger.debug(f"Removed {self.tag_name} tag from {asg_name}")
                            return True
                        else:
                            return True
                        
                    except ValueError as e:
                        logger.error(f"Error parsing scaling values for ASG {asg_name}: {str(e)}")
                        return False
                else:
                    logger.debug(f"No {self.tag_name} tag found for ASG: {asg_name}")
                    return False
                
        except ClientError as e:
            logger.error(f"Error processing ASG {asg_name}: {str(e)}")
            return False

    def _manage_aws_node_groups(self) -> None:
        """Manage AWS Auto Scaling Groups for the specified cluster.
        
        This method:
        - If scale_down=True: Saves current state and scales down to 0
        - If scale_down=False: Checks for OffHoursPrevious tags and scales up
        
        Raises:
            ClientError: If AWS API calls fail
            ValueError: If tag parsing fails
        """
        try:
            logger.debug(f"Starting AWS node group management for cluster: {self.cluster_name}")
            
            # Get AWS clients
            autoscaling = self._get_aws_client('autoscaling')
            
            # Get all ASGs
            logger.info("Searching for Auto Scaling Groups...")
            paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
            asg_count = 0
            matching_asgs = []
            
            for page in paginator.paginate():
                for asg in page['AutoScalingGroups']:
                    asg_count += 1
                    asg_name = asg['AutoScalingGroupName']
                    logger.debug(f"Found ASG: {asg_name}")
                    
                    # Check if ASG name contains cluster name
                    if self.cluster_name in asg_name:
                        matching_asgs.append(asg)
                        logger.debug(f"Found matching ASG: {asg_name}")
            
            matching_asg_count = len(matching_asgs)
            
            # Process ASGs in parallel
            processed_count = 0
            if matching_asgs:
                logger.info(f"Processing {matching_asg_count} ASGs in parallel...")
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(self._process_aws_asg, asg): asg for asg in matching_asgs}
                    
                    for future in as_completed(futures):
                        asg = futures[future]
                        try:
                            was_processed = future.result()
                            if was_processed:
                                processed_count += 1
                        except Exception as e:
                            logger.error(f"Error processing ASG {asg['AutoScalingGroupName']}: {str(e)}")
            
            # Summary
            logger.info("")
            logger.info("=" * 60)
            if self.dry_run:
                logger.info("SUMMARY (DRY RUN - No changes were made)")
            else:
                logger.info("SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Total ASGs scanned: {asg_count}")
            logger.info(f"ASGs matching cluster '{self.cluster_name}': {matching_asg_count}")
            
            if self.dry_run:
                # In dry run, count operations that would be performed (filter by AWS provider)
                aws_operations = [op for op in self.operations if op.provider == CloudProvider.AWS]
                would_update_count = len(aws_operations)
                if would_update_count > 0:
                    logger.info(f"ASGs that would be updated: {would_update_count}")
                    for op in aws_operations:
                        if self.scale_down:
                            logger.info(f"  - {op.resource_name}: {op.current_size} → 0 nodes (saving state: min={op.min_size}, max={op.max_size}, desired={op.current_size})")
                        else:
                            logger.info(f"  - {op.resource_name}: {op.current_size} → {op.target_size} nodes (min={op.min_size}, max={op.max_size})")
                elif matching_asg_count > 0:
                    if self.scale_down:
                        logger.info("No ASGs would be updated (already at 0 or no matching ASGs)")
                    else:
                        logger.info("No ASGs would be updated (no OffHoursPrevious tags found)")
                else:
                    logger.warning(f"No ASGs found matching cluster name: {self.cluster_name}")
            else:
                # Normal execution
                if processed_count > 0:
                    logger.info(f"ASGs successfully updated: {processed_count}")
                elif matching_asg_count > 0:
                    if self.scale_down:
                        logger.info("No ASGs required updates (already at 0 or no matching ASGs)")
                    else:
                        logger.info("No ASGs required updates (no OffHoursPrevious tags found)")
                else:
                    logger.warning(f"No ASGs found matching cluster name: {self.cluster_name}")
            logger.info("=" * 60)
                        
        except ClientError as e:
            logger.error(f"AWS API error: {str(e)}")
            raise

    def _scale_down_aws_asg(self, autoscaling, asg: Dict, asg_name: str) -> bool:
        """Scale down an AWS ASG to 0 and save current state.
        
        Args:
            autoscaling: AWS autoscaling client
            asg: ASG dictionary from describe_auto_scaling_groups
            asg_name: Name of the ASG
            
        Returns:
            bool: True if the ASG was processed, False otherwise
        """
        current_min = asg['MinSize']
        current_max = asg['MaxSize']
        current_desired = asg['DesiredCapacity']
        
        # Check if already at 0
        if current_desired == 0 and current_min == 0 and current_max == 0:
            logger.debug(f"ASG {asg_name} is already scaled down to 0")
            return False
        
        # Create tag value in AWS format
        tag_value = f"MaxSize={current_max};DesiredCapacity={current_desired};MinSize={current_min}"
        
        # Add operation to the list
        operation = ScalingOperation(
            resource_name=asg_name,
            current_size=current_desired,
            target_size=0,
            min_size=current_min,
            max_size=current_max,
            provider=CloudProvider.AWS
        )
        self._add_operation(operation)
        
        if not self.dry_run:
            # Save current state to tag
            logger.info(f"  → Saving state for {asg_name}: min={current_min}, max={current_max}, desired={current_desired}")
            autoscaling.create_or_update_tags(
                Tags=[
                    {
                        'ResourceId': asg_name,
                        'ResourceType': 'auto-scaling-group',
                        'Key': self.tag_name,
                        'Value': tag_value,
                        'PropagateAtLaunch': False
                    }
                ]
            )
            logger.debug(f"Saved current state to {self.tag_name} tag: {tag_value}")
            
            # Scale down to 0
            logger.info(f"  → Scaling down {asg_name} to 0 nodes")
            autoscaling.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0,
                MaxSize=0,
                DesiredCapacity=0
            )
            logger.info(f"  ✓ Successfully scaled down {asg_name} to 0")
            return True
        
        return True

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
            
            # Handle status as both enum and integer for compatibility
            status = operation_response.status
            status_value = status.value if hasattr(status, 'value') else int(status)
            
            # Status enum values: STATUS_UNSPECIFIED=0, PENDING=1, RUNNING=2, DONE=3, ABORTING=4
            if status_value == 3 or status == container_v1.Operation.Status.DONE:
                logger.info("Operation completed successfully.")
                return
            elif status_value == 2 or status == container_v1.Operation.Status.RUNNING:
                logger.info("Operation is still running...")
                time.sleep(5)
            elif status_value == 1 or status == container_v1.Operation.Status.PENDING:
                logger.info("Operation is pending...")
                time.sleep(5)
            elif status_value == 4 or status == container_v1.Operation.Status.ABORTING:
                logger.warning("Operation is aborting.")
                return
            elif status_value == 0:
                # STATUS_UNSPECIFIED - treat as pending and continue waiting
                logger.debug("Operation status unspecified, continuing to wait...")
                time.sleep(5)
            else:
                # Log as warning instead of error for unknown but potentially valid statuses
                logger.warning(f"Unknown operation status: {status_value} (operation: {operation_name})")
                time.sleep(5)

        raise TimeoutError(f"Operation {operation_name} timed out after {timeout_seconds} seconds.")

    def _manage_gcp_node_groups(self) -> None:
        """Manage GCP node pools for the specified cluster.
        
        This method:
        - If scale_down=True: Saves current state and scales down to 0
        - If scale_down=False: Checks for offhoursprevious labels and scales up
        
        Raises:
            google_exceptions.GoogleAPIError: If GCP API calls fail
            ValueError: If tag parsing fails
        """
        try:
            logger.debug(f"Starting GCP node group management for cluster: {self.cluster_name}")
            
            client = container_v1.ClusterManagerClient()
            project_id = self.account
            parent = f"projects/{project_id}/locations/-"
            
            try:
                logger.info("Searching for GKE clusters...")
                clusters = client.list_clusters(parent=parent)
                
                cluster_found = False
                node_pool_count = 0
                matching_node_pool_count = 0
                processed_count = 0
                
                for cluster in clusters.clusters:
                    if cluster.name == self.cluster_name:
                        cluster_found = True
                        logger.debug(f"Found matching cluster: {cluster.name} in {cluster.location}")
                        node_pool_count = len(cluster.node_pools)
                        matching_node_pool_count = node_pool_count
                        
                        # Process node pools in parallel
                        if cluster.node_pools:
                            logger.info(f"Processing {node_pool_count} node pools in parallel...")
                            with ThreadPoolExecutor(max_workers=5) as executor:
                                futures = {executor.submit(self._process_gcp_node_pool, client, project_id, cluster, node_pool): node_pool 
                                          for node_pool in cluster.node_pools}
                                
                                for future in as_completed(futures):
                                    node_pool = futures[future]
                                    try:
                                        was_processed = future.result()
                                        if was_processed:
                                            processed_count += 1
                                    except google_exceptions.GoogleAPIError as e:
                                        logger.error(f"Error processing node pool {node_pool.name}: {str(e)}")
                                    except Exception as e:
                                        logger.error(f"Unexpected error processing node pool {node_pool.name}: {str(e)}")
                        
                        break
                
                # Summary
                logger.info("")
                logger.info("=" * 60)
                if self.dry_run:
                    logger.info("SUMMARY (DRY RUN - No changes were made)")
                else:
                    logger.info("SUMMARY")
                logger.info("=" * 60)
                if cluster_found:
                    logger.info(f"Cluster found: {self.cluster_name}")
                    logger.info(f"Total node pools in cluster: {node_pool_count}")
                    logger.info(f"Node pools processed: {matching_node_pool_count}")
                    
                    if self.dry_run:
                        # In dry run, count operations that would be performed (filter by GCP provider)
                        gcp_operations = [op for op in self.operations if op.provider == CloudProvider.GCP]
                        would_update_count = len(gcp_operations)
                        if would_update_count > 0:
                            logger.info(f"Node pools that would be updated: {would_update_count}")
                            for op in gcp_operations:
                                if self.scale_down:
                                    logger.info(f"  - {op.resource_name}: {op.current_size} → 0 nodes (saving state: min={op.min_size}, max={op.max_size}, desired={op.current_size})")
                                else:
                                    logger.info(f"  - {op.resource_name}: {op.current_size} → {op.target_size} nodes (min={op.min_size}, max={op.max_size})")
                        elif matching_node_pool_count > 0:
                            if self.scale_down:
                                logger.info("No node pools would be updated (already at 0 or no matching node pools)")
                            else:
                                logger.info("No node pools would be updated (no offhoursprevious labels found)")
                    else:
                        # Normal execution
                        if processed_count > 0:
                            logger.info(f"Node pools successfully updated: {processed_count}")
                        elif matching_node_pool_count > 0:
                            if self.scale_down:
                                logger.info("No node pools required updates (already at 0 or no matching node pools)")
                            else:
                                logger.info("No node pools required updates (no offhoursprevious labels found)")
                else:
                    logger.warning(f"Cluster '{self.cluster_name}' not found in project '{project_id}'")
                logger.info("=" * 60)
                                
            except google_exceptions.GoogleAPIError as e:
                logger.error(f"Error listing clusters: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"GCP API error: {str(e)}")
            raise

    def _process_gcp_node_pool(self, client: container_v1.ClusterManagerClient, project_id: str, cluster: Any, node_pool: Any) -> bool:
        """Process a single GCP node pool.
        
        Args:
            client: The GKE ClusterManagerClient
            project_id: The GCP project ID
            cluster: The GKE cluster
            node_pool: The node pool to process
            
        Returns:
            bool: True if the node pool was processed/updated, False otherwise
        """
        node_pool_name = f"projects/{project_id}/locations/{cluster.location}/clusters/{cluster.name}/nodePools/{node_pool.name}"
        node_pool_details = client.get_node_pool(name=node_pool_name)
        
        if self.scale_down:
            # Scale down mode: save current state and scale to 0
            return self._scale_down_gcp_node_pool(client, node_pool_name, project_id, cluster, node_pool, node_pool_details)
        else:
            # Scale up mode: restore from offhoursprevious label
            current_labels = dict(node_pool_details.config.labels)
            
            # Check for offhoursprevious in labels
            if self.tag_name in node_pool_details.config.labels:
                off_hours_previous = node_pool_details.config.labels[self.tag_name]
                logger.debug(f"Found {self.tag_name} label for node pool: {node_pool.name}")
                
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
                        logger.info(f"  → Updating {node_pool.name}: scaling from {node_pool.initial_node_count} to {desired_capacity} nodes (min={min_size}, max={max_size})")
                        self._execute_gcp_scaling(client, node_pool_name, project_id, cluster.location, 
                                               desired_capacity, min_size, max_size, current_labels, node_pool=node_pool)
                        logger.info(f"  ✓ Successfully updated {node_pool.name}")
                        return True
                    else:
                        return True
                        
                except ValueError as e:
                    logger.error(f"Error parsing scaling values for node pool {node_pool.name}: {str(e)}")
                except google_exceptions.GoogleAPIError as e:
                    logger.error(f"Error updating node pool {node_pool.name}: {str(e)}")
            
            return False

    def _resize_single_instance_group(self, project_id: str, instance_group_url: str, target_size: int) -> None:
        """Resize a single GCP instance group.
        
        Args:
            project_id: The GCP project ID
            instance_group_url: The instance group URL
            target_size: Target size for the instance group
        """
        # Parse the instance group URL to extract zone and name
        # Format: https://www.googleapis.com/compute/v1/projects/PROJECT/zones/ZONE/instanceGroupManagers/NAME
        url_parts = instance_group_url.split('/')
        if len(url_parts) < 9:
            logger.warning(f"Invalid instance group URL format: {instance_group_url}")
            return
        
        zone = url_parts[8]  # Zone is at index 8
        igm_name = url_parts[-1]  # Name is the last part
        
        logger.debug(f"Resizing instance group {igm_name} in zone {zone} to {target_size}")
        
        if not self.dry_run:
            with compute_v1.InstanceGroupManagersClient() as igm_client:
                resize_request = compute_v1.ResizeInstanceGroupManagerRequest(
                    instance_group_manager=igm_name,
                    project=project_id,
                    size=target_size,
                    zone=zone
                )
                igm_resize_operation = igm_client.resize(request=resize_request)
                logger.info(f"  → Resized instance group {igm_name} to {target_size}. Operation: {igm_resize_operation.name}")
        else:
            logger.info(f"  [DRY RUN] Would resize instance group {igm_name} to {target_size}")

    def _resize_instance_groups(self, project_id: str, node_pool: Any, target_size: int) -> None:
        """Resize GCP instance groups associated with a node pool in parallel.
        
        Args:
            project_id: The GCP project ID
            node_pool: The node pool object containing instance_group_urls
            target_size: Target size for the instance groups (0 for scale down)
        """
        if not hasattr(node_pool, 'instance_group_urls') or not node_pool.instance_group_urls:
            logger.debug(f"No instance group URLs found for node pool {node_pool.name}")
            return
        
        instance_group_urls = node_pool.instance_group_urls
        if len(instance_group_urls) == 1:
            # Single instance group, no need for parallelization
            self._resize_single_instance_group(project_id, instance_group_urls[0], target_size)
        else:
            # Multiple instance groups, process in parallel
            logger.debug(f"Resizing {len(instance_group_urls)} instance groups in parallel...")
            try:
                with ThreadPoolExecutor(max_workers=len(instance_group_urls)) as executor:
                    futures = {executor.submit(self._resize_single_instance_group, project_id, url, target_size): url 
                              for url in instance_group_urls}
                    
                    for future in as_completed(futures):
                        url = futures[future]
                        try:
                            future.result()
                        except google_exceptions.GoogleAPIError as e:
                            logger.error(f"Error resizing instance group {url}: {str(e)}")
                        except Exception as e:
                            logger.error(f"Unexpected error resizing instance group {url}: {str(e)}")
            except Exception as e:
                logger.error(f"Error resizing instance groups: {str(e)}")
                raise

    def _scale_down_gcp_node_pool(self, client: container_v1.ClusterManagerClient, node_pool_name: str, 
                                  project_id: str, cluster: Any, node_pool: Any, node_pool_details: Any) -> bool:
        """Scale down a GCP node pool to 0 and save current state.
        
        Args:
            client: The GKE ClusterManagerClient
            node_pool_name: Full name of the node pool
            project_id: The GCP project ID
            cluster: The GKE cluster
            node_pool: The node pool object
            node_pool_details: The detailed node pool information
            
        Returns:
            bool: True if the node pool was processed, False otherwise
        """
        # Get current scaling values (handle case where autoscaling is disabled)
        if node_pool.autoscaling and node_pool.autoscaling.enabled:
            current_min = node_pool.autoscaling.min_node_count
            current_max = node_pool.autoscaling.max_node_count
        else:
            # Autoscaling is disabled, use initial_node_count for both min and max
            current_min = node_pool.initial_node_count
            current_max = node_pool.initial_node_count
        
        current_desired = node_pool.initial_node_count
        
        # Check if already at 0
        if current_desired == 0 and current_min == 0 and current_max == 0:
            logger.debug(f"Node pool {node_pool.name} is already scaled down to 0")
            return False
        
        # Get current labels for saving state
        current_labels = dict(node_pool_details.config.labels)
        
        # Create label value in GCP format
        label_value = (
            f"maxsize{current_max}-"
            f"desiredcapacity{current_desired}-"
            f"minsize{current_min}"
        )
        
        # Add operation to the list
        operation = ScalingOperation(
            resource_name=node_pool.name,
            current_size=current_desired,
            target_size=0,
            min_size=current_min,
            max_size=current_max,
            provider=CloudProvider.GCP
        )
        self._add_operation(operation)
        
        if not self.dry_run:
            # Save current state to label
            logger.info(f"  → Saving state for {node_pool.name}: min={current_min}, max={current_max}, desired={current_desired}")
            current_labels[self.tag_name] = label_value
            update_request = container_v1.UpdateNodePoolRequest(
                name=node_pool_name,
                labels=container_v1.NodeLabels(labels=current_labels)
            )
            operation = client.update_node_pool(request=update_request)
            logger.debug(f"Saved current state to {self.tag_name} label: {label_value}")
            self._wait_for_operation(client, project_id, cluster.location, operation.name.split('/')[-1])
            
            # Scale down to 0
            logger.info(f"  → Scaling down {node_pool.name} to 0 nodes")
            self._execute_gcp_scaling(client, node_pool_name, project_id, cluster.location, 
                                    0, 0, 0, current_labels, remove_label=False)
            
            # Resize instance groups to 0
            logger.info(f"  → Resizing instance groups for {node_pool.name} to 0")
            self._resize_instance_groups(project_id, node_pool, 0)
            
            logger.info(f"  ✓ Successfully scaled down {node_pool.name} to 0")
            return True
        
        return True

    def _execute_gcp_scaling(self, client: container_v1.ClusterManagerClient, node_pool_name: str, 
                           project_id: str, location: str, desired_capacity: int, 
                           min_size: int, max_size: int, current_labels: Dict[str, str], 
                           remove_label: bool = True, node_pool: Any = None) -> None:
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
            remove_label: If True, remove the offhoursprevious label after scaling (default: True)
            node_pool: The node pool object (optional, needed for instance group scaling)
        """
        # Set node pool size
        size_request = container_v1.SetNodePoolSizeRequest(
            name=node_pool_name,
            node_count=desired_capacity
        )
        operation = client.set_node_pool_size(request=size_request)
        logger.debug(f"Setting node pool size to {desired_capacity}")
        self._wait_for_operation(client, project_id, location, operation.name.split('/')[-1])
        
        # Enable autoscaling (or disable if min=max=0)
        if min_size == 0 and max_size == 0:
            # Disable autoscaling when scaling to 0
            autoscaling_request = container_v1.SetNodePoolAutoscalingRequest(
                name=node_pool_name,
                autoscaling=container_v1.NodePoolAutoscaling(
                    enabled=False
                )
            )
            logger.debug("Disabling autoscaling (scaled to 0)")
        else:
            # Enable autoscaling with specified limits
            autoscaling_request = container_v1.SetNodePoolAutoscalingRequest(
                name=node_pool_name,
                autoscaling=container_v1.NodePoolAutoscaling(
                    enabled=True,
                    min_node_count=min_size,
                    max_node_count=max_size
                )
            )
            logger.debug("Enabling autoscaling")
        operation = client.set_node_pool_autoscaling(request=autoscaling_request)
        self._wait_for_operation(client, project_id, location, operation.name.split('/')[-1])
        
        # Resize instance groups if node_pool is provided and we're scaling up (not to 0)
        if node_pool and desired_capacity > 0:
            logger.info(f"  → Resizing instance groups to {desired_capacity}")
            # Get updated node pool to ensure we have the latest instance_group_urls
            updated_node_pool = client.get_node_pool(name=node_pool_name)
            self._resize_instance_groups(project_id, updated_node_pool, desired_capacity)
        
        # Remove the offhoursprevious label if requested (only in scale-up mode)
        if remove_label:
            current_labels.pop(self.tag_name, None)
            update_request = container_v1.UpdateNodePoolRequest(
                name=node_pool_name,
                labels=container_v1.NodeLabels(labels=current_labels)
            )
            operation = client.update_node_pool(request=update_request)
            logger.debug(f"Removing {self.tag_name} label")
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
        '--scale-down',
        action='store_true',
        help='Scale down to 0 and save current state (opposite of scale up)'
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
            dry_run=args.dry_run,
            scale_down=args.scale_down
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