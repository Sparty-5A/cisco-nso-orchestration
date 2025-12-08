"""
Intent reconciliation engine for network configuration.

This module compares desired state (intent) with actual state (from devices)
and calculates the minimal set of changes needed to achieve the intent.
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from automation.device_models import (
    DeviceIntent,
    NetworkIntent,
)
from automation.nso_client import NSOClient
from services.bgp_peering import (
    check_bgp_configured,
    deploy_bgp_service,
    remove_bgp_service,
)
from automation.service_models import (
    BGPPeeringServiceIntent,
    BGPNeighborIntent,
)


@dataclass
class Change:
    """Represents a single configuration change."""

    action: str  # "create", "update", "delete"
    device: str
    resource_type: str  # "loopback", "bgp", etc.
    resource_id: str
    current: dict[str, Any] | None
    desired: dict[str, Any] | None

    def __str__(self) -> str:
        if self.action == "create":
            return f"[{self.device}] CREATE {self.resource_type} {self.resource_id}"
        elif self.action == "delete":
            return f"[{self.device}] DELETE {self.resource_type} {self.resource_id}"
        else:
            return f"[{self.device}] UPDATE {self.resource_type} {self.resource_id}"


class DeviceEngine:
    """Engine for reconciling network intent with actual state."""

    def __init__(self, nso_client: NSOClient, inventory=None):
        """
        Initialize intent engine.

        Args:
            nso_client: NSO client for querying and configuring devices
            inventory: Optional inventory for device metadata
        """
        self.client = nso_client
        self.inventory = inventory

    def get_current_loopbacks(self, device_name: str) -> dict[str, dict[str, Any]]:
        """
        Get current loopback configuration from device.

        Args:
            device_name: Name of device to query

        Returns:
            Dict mapping loopback ID to configuration
            Example: {"100": {"ip": "10.100.100.1", "netmask": "255.255.255.255", "description": "Mgmt"}}
        """
        logger.info(f"Querying current loopbacks from {device_name}")

        # Sync device first to get latest config
        self.client.sync_from_device(device_name)

        # Get full device config
        config = self.client.get_device_config(device_name)
        if not config:
            logger.warning(f"Could not retrieve config from {device_name}")
            return {}

        # Extract loopbacks from config
        loopbacks = {}

        try:
            # Navigate to interface config (structure varies by NED)
            interfaces = (
                config.get("tailf-ncs:config", {})
                .get("tailf-ned-cisco-ios:interface", {})
                .get("Loopback", [])
            )

            for lb in interfaces:
                lb_id = lb.get("name")
                if not lb_id:
                    continue

                # Extract IP config
                ip_config = lb.get("ip", {}).get("address", {}).get("primary", {})

                loopbacks[str(lb_id)] = {
                    "ip": ip_config.get("address"),
                    "netmask": ip_config.get("mask"),
                    "description": lb.get("description"),
                }

                logger.debug(f"Found Loopback{lb_id}: {loopbacks[lb_id]}")

        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing loopback config from {device_name}: {e}")
            return {}

        logger.info(f"Found {len(loopbacks)} loopbacks on {device_name}")
        return loopbacks

    def calculate_loopback_changes(self, device_intent: DeviceIntent) -> list[Change]:
        """
        Calculate changes needed to achieve desired loopback state.

        Args:
            device_intent: Device intent including loopback config and deletion policy

        Returns:
            List of changes needed
        """
        changes = []
        device_name = device_intent.name
        desired_loopbacks = device_intent.loopbacks
        delete_unmanaged = device_intent.delete_unmanaged_loopbacks

        # Get current state
        current_loopbacks = self.get_current_loopbacks(device_name)

        # Build desired state map
        desired_map = {str(lb.id): lb for lb in desired_loopbacks}

        # Find creates and updates
        for lb_id, desired_lb in desired_map.items():
            if lb_id not in current_loopbacks:
                # CREATE: Loopback doesn't exist
                changes.append(
                    Change(
                        action="create",
                        device=device_name,
                        resource_type="loopback",
                        resource_id=lb_id,
                        current=None,
                        desired={
                            "ip": desired_lb.ipv4,
                            "netmask": desired_lb.netmask,
                            "description": desired_lb.description,
                        },
                    )
                )
            else:
                # Check if UPDATE needed
                current = current_loopbacks[lb_id]
                needs_update = False

                if current.get("ip") != desired_lb.ipv4:
                    needs_update = True
                if current.get("netmask") != desired_lb.netmask:
                    needs_update = True
                if current.get("description") != desired_lb.description:
                    needs_update = True

                if needs_update:
                    changes.append(
                        Change(
                            action="update",
                            device=device_name,
                            resource_type="loopback",
                            resource_id=lb_id,
                            current=current,
                            desired={
                                "ip": desired_lb.ipv4,
                                "netmask": desired_lb.netmask,
                                "description": desired_lb.description,
                            },
                        )
                    )

        # Find deletes (loopbacks that exist but aren't in intent)
        # Only delete if explicitly enabled
        unmanaged_loopbacks = [lb_id for lb_id in current_loopbacks if lb_id not in desired_map]

        if unmanaged_loopbacks:
            if delete_unmanaged:
                logger.warning(
                    f"[{device_name}] delete_unmanaged_loopbacks=True: "
                    f"Will DELETE {len(unmanaged_loopbacks)} loopbacks not in intent: {unmanaged_loopbacks}"
                )
                for lb_id in unmanaged_loopbacks:
                    changes.append(
                        Change(
                            action="delete",
                            device=device_name,
                            resource_type="loopback",
                            resource_id=lb_id,
                            current=current_loopbacks[lb_id],
                            desired=None,
                        )
                    )
            else:
                logger.info(
                    f"[{device_name}] delete_unmanaged_loopbacks=False (safe mode): "
                    f"Ignoring {len(unmanaged_loopbacks)} unmanaged loopbacks: {unmanaged_loopbacks}"
                )

        return changes

    def calculate_bgp_changes(self, device_intent: DeviceIntent) -> list[Change]:
        """
        Calculate changes needed to achieve desired BGP state.

        Args:
            device_intent: Device intent including BGP config

        Returns:
            List of changes needed
        """
        changes = []
        device_name = device_intent.name

        if not device_intent.bgp:
            # No BGP intent - check if we should remove existing BGP
            logger.debug(f"[{device_name}] No BGP intent specified")
            return changes

        # Convert device_models.BGPIntent to service_models.BGPPeeringServiceIntent
        # for compatibility with existing bgp_peering.py functions
        bgp_intent = device_intent.bgp

        service_intent = BGPPeeringServiceIntent(
            local_as=bgp_intent.asn,
            router_id=bgp_intent.router_id if bgp_intent.router_id else "0.0.0.0",
            neighbors=[
                BGPNeighborIntent(
                    neighbor_ip=n.ip,           # device model uses 'ip'
                    remote_as=n.remote_asn,     # device model uses 'remote_asn'
                    description=n.description,
                    update_source=n.update_source,
                )
                for n in bgp_intent.neighbors
            ],
        )

        # Check if BGP is already configured correctly
        is_configured = check_bgp_configured(self.client, device_name, service_intent)

        if not is_configured:
            # BGP needs to be created or updated
            changes.append(
                Change(
                    action="create",  # We treat BGP as create/update combined
                    device=device_name,
                    resource_type="bgp",
                    resource_id=str(bgp_intent.asn),
                    current=None,
                    desired={
                        "asn": bgp_intent.asn,
                        "router_id": bgp_intent.router_id,
                        "neighbors": [n.model_dump() for n in bgp_intent.neighbors],
                    },
                )
            )
        else:
            logger.info(f"[{device_name}] BGP AS {bgp_intent.asn} already configured correctly")

            # Check if we need to remove unmanaged neighbors
            if device_intent.delete_unmanaged_bgp_neighbors:
                # Get current BGP config
                self.client.sync_from_device(device_name)
                config = self.client.get_device_config(device_name)

                if config:
                    bgp_config = (
                        config.get("tailf-ncs:config", {})
                        .get("tailf-ned-cisco-ios:router", {})
                        .get("bgp", [])  # BGP is a list!
                    )

                    if bgp_config:
                        # BGP is a list - find the process matching our AS
                        if not isinstance(bgp_config, list):
                            bgp_config = [bgp_config]

                        # Find BGP process with matching AS
                        bgp_process = None
                        for process in bgp_config:
                            if str(process.get("as-no")) == str(bgp_intent.asn):
                                bgp_process = process
                                break

                        if bgp_process:
                            # Get current neighbors
                            current_neighbors = bgp_process.get("neighbor", [])
                            if not isinstance(current_neighbors, list):
                                current_neighbors = [current_neighbors] if current_neighbors else []

                            current_neighbor_ips = {n.get("id") for n in current_neighbors}

                            # Get desired neighbors from intent
                            desired_neighbor_ips = {n.ip for n in bgp_intent.neighbors}

                            # Find unmanaged neighbors
                            unmanaged_neighbors = current_neighbor_ips - desired_neighbor_ips

                            if unmanaged_neighbors:
                                logger.warning(
                                    f"[{device_name}] delete_unmanaged_bgp_neighbors=True: "
                                    f"Will DELETE {len(unmanaged_neighbors)} BGP neighbors not in intent: "
                                    f"{unmanaged_neighbors}"
                                )

                                for neighbor_ip in unmanaged_neighbors:
                                    changes.append(
                                        Change(
                                            action="delete",
                                            device=device_name,
                                            resource_type="bgp-neighbor",
                                            resource_id=neighbor_ip,
                                            current={"neighbor_ip": neighbor_ip},
                                            desired=None,
                                        )
                                    )
                            else:
                                logger.info(
                                    f"[{device_name}] No unmanaged BGP neighbors to delete"
                                )
            else:
                # Safe mode - just log if there are unmanaged neighbors
                self.client.sync_from_device(device_name)
                config = self.client.get_device_config(device_name)

                if config:
                    bgp_config = (
                        config.get("tailf-ncs:config", {})
                        .get("tailf-ned-cisco-ios:router", {})
                        .get("bgp", [])  # BGP is a list!
                    )

                    if bgp_config:
                        # BGP is a list - find the process matching our AS
                        if not isinstance(bgp_config, list):
                            bgp_config = [bgp_config]

                        # Find BGP process with matching AS
                        bgp_process = None
                        for process in bgp_config:
                            if str(process.get("as-no")) == str(bgp_intent.asn):
                                bgp_process = process
                                break

                        if bgp_process:
                            current_neighbors = bgp_process.get("neighbor", [])
                            if not isinstance(current_neighbors, list):
                                current_neighbors = [current_neighbors] if current_neighbors else []

                            current_neighbor_ips = {n.get("id") for n in current_neighbors}
                            desired_neighbor_ips = {n.ip for n in bgp_intent.neighbors}
                            unmanaged_neighbors = current_neighbor_ips - desired_neighbor_ips

                            if unmanaged_neighbors:
                                logger.info(
                                    f"[{device_name}] delete_unmanaged_bgp_neighbors=False (safe mode): "
                                    f"Ignoring {len(unmanaged_neighbors)} unmanaged BGP neighbors: "
                                    f"{unmanaged_neighbors}"
                                )

        return changes

    def calculate_changes(self, intent: NetworkIntent) -> list[Change]:
        """
        Calculate all changes needed to achieve network intent.

        Args:
            intent: Desired network state

        Returns:
            List of all changes across all devices
        """
        all_changes = []

        for device_intent in intent.devices:
            logger.info(f"Calculating changes for {device_intent.name}")

            # Calculate loopback changes
            loopback_changes = self.calculate_loopback_changes(device_intent)
            all_changes.extend(loopback_changes)

            # Calculate BGP changes
            bgp_changes = self.calculate_bgp_changes(device_intent)
            all_changes.extend(bgp_changes)

        return all_changes

    def apply_change(self, change: Change, dry_run: bool = False) -> bool:
        """
        Apply a single configuration change.

        Args:
            change: Change to apply
            dry_run: If True, only show what would change

        Returns:
            True if successful
        """
        if dry_run:
            logger.info(f"[DRY-RUN] Would apply: {change}")
            return True

        logger.info(f"Applying: {change}")

        if change.resource_type == "loopback":
            if change.action in ("create", "update"):
                # Configure loopback
                success = self.client.configure_loopback(
                    device_name=change.device,
                    loopback_id=change.resource_id,
                    ip_address=change.desired["ip"],
                    netmask=change.desired["netmask"],
                    description=change.desired.get("description"),
                )
                return success

            elif change.action == "delete":
                # Delete loopback
                success = self.client.delete_loopback(
                    device_name=change.device, loopback_id=change.resource_id
                )
                return success

        elif change.resource_type == "bgp":
            if change.action in ("create", "update"):
                # Get device from inventory to determine device type
                device = None
                if self.inventory:
                    device = self.inventory.get_device(change.device)

                # Convert back to BGPPeeringServiceIntent for deployment
                service_intent = BGPPeeringServiceIntent(
                    local_as=change.desired["asn"],
                    router_id=change.desired["router_id"],
                    neighbors=[
                        BGPNeighborIntent(
                            neighbor_ip=n["ip"],          # Extract from dict correctly
                            remote_as=n["remote_asn"],    # Extract from dict correctly
                            description=n.get("description"),
                            update_source=n.get("update_source"),
                        )
                        for n in change.desired["neighbors"]
                    ],
                )

                # Deploy BGP
                success, message = deploy_bgp_service(
                    self.client,
                    change.device,
                    service_intent,
                    dry_run=False,
                    inventory=self.inventory,
                )

                if success:
                    logger.info(f"[{change.device}] ✓ {message}")
                else:
                    logger.error(f"[{change.device}] ✗ {message}")

                return success

            elif change.action == "delete":
                # Remove BGP
                success, message = remove_bgp_service(
                    self.client, change.device, int(change.resource_id), dry_run=False
                )
                return success

        elif change.resource_type == "bgp-neighbor":
            if change.action == "delete":
                # Delete specific BGP neighbor
                logger.info(f"[{change.device}] Deleting BGP neighbor {change.resource_id}")

                # Determine device type for correct NED namespace
                device = None
                if self.inventory:
                    device = self.inventory.get_device(change.device)

                # Build URL for neighbor deletion
                if device and device.device_type == "ios-xr":
                    ned_namespace = "tailf-ned-cisco-ios-xr"
                else:
                    ned_namespace = "tailf-ned-cisco-ios"

                # Get BGP AS from current config
                config = self.client.get_device_config(change.device)
                if config:
                    bgp_config = (
                        config.get("tailf-ncs:config", {})
                        .get(f"{ned_namespace}:router", {})
                        .get("bgp", {})
                    )
                    as_number = bgp_config.get("as-no")

                    if as_number:
                        url = (
                            f"{self.client.base_url}/data/tailf-ncs:devices/"
                            f"device={change.device}/config/{ned_namespace}:router/"
                            f"bgp={as_number}/neighbor={change.resource_id}"
                        )

                        resp = self.client._safe_delete(url)

                        if resp and resp.status_code in (200, 204):
                            logger.info(
                                f"[{change.device}] ✓ BGP neighbor {change.resource_id} deleted"
                            )
                            return True
                        else:
                            logger.error(
                                f"[{change.device}] ✗ Failed to delete BGP neighbor {change.resource_id}"
                            )
                            return False

                logger.error(f"[{change.device}] Could not determine BGP AS for neighbor deletion")
                return False

        return False

    def apply_intent(self, intent: NetworkIntent, dry_run: bool = False) -> tuple[int, int]:
        """
        Apply network intent - reconcile desired state with actual state.

        Args:
            intent: Desired network state
            dry_run: If True, only show what would change without applying

        Returns:
            Tuple of (successful_changes, failed_changes)
        """
        logger.info("=" * 70)
        logger.info(f"{'DRY-RUN: ' if dry_run else ''}Applying network intent")
        logger.info("=" * 70)

        # Calculate changes
        changes = self.calculate_changes(intent)

        if not changes:
            logger.info("✓ No changes needed - network is in desired state")
            return 0, 0

        # Show summary
        creates = [c for c in changes if c.action == "create"]
        updates = [c for c in changes if c.action == "update"]
        deletes = [c for c in changes if c.action == "delete"]

        logger.info(f"Planned changes: {len(changes)} total")
        if creates:
            logger.info(f"  - {len(creates)} creates")
        if updates:
            logger.info(f"  - {len(updates)} updates")
        if deletes:
            logger.info(f"  - {len(deletes)} deletes")
        logger.info("")

        # Apply changes
        success_count = 0
        failure_count = 0

        for change in changes:
            try:
                if self.apply_change(change, dry_run=dry_run):
                    success_count += 1
                else:
                    failure_count += 1
                    logger.error(f"✗ Failed to apply: {change}")
            except Exception as e:
                failure_count += 1
                logger.error(f"✗ Exception applying {change}: {e}")

        # Summary
        logger.info("")
        logger.info("=" * 70)
        if dry_run:
            logger.info(f"DRY-RUN Complete: {success_count} changes would be applied")
        else:
            logger.info(
                f"Intent reconciliation complete: {success_count} succeeded, {failure_count} failed"
            )
        logger.info("=" * 70)

        return success_count, failure_count