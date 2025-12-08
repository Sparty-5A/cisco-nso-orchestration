"""
Service orchestrator for multi-device service deployment.

This module coordinates service deployment across multiple devices with:
- Parallel execution
- Inventory integration
- Validation and rollback
- Progress tracking
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from loguru import logger

from automation.inventory_loader import Inventory
from automation.nso_client import NSOClient
from automation.service_models import ServiceDeploymentIntent
from services.bgp_peering import (
    check_bgp_configured,
    deploy_bgp_service,
    remove_bgp_service,
)


@dataclass
class ServiceDeploymentResult:
    """Result of a service deployment to a single device."""

    device_name: str
    service_type: str
    success: bool
    message: str
    changed: bool = False
    rollback_id: int | None = None


class ServiceOrchestrator:
    """Orchestrates service deployment across multiple devices."""

    def __init__(
        self,
        nso_client: NSOClient,
        inventory: Inventory | None = None,
        max_workers: int = 5,
    ):
        """
        Initialize service orchestrator.

        Args:
            nso_client: NSO client for device operations
            inventory: Device inventory (optional, for filtering/enrichment)
            max_workers: Maximum parallel deployments (default: 5)
        """
        self.client = nso_client
        self.inventory = inventory
        self.max_workers = max_workers

    def _deploy_to_device(
        self, device_name: str, intent: ServiceDeploymentIntent, dry_run: bool = False
    ) -> ServiceDeploymentResult:
        """
        Deploy service to a single device.

        Args:
            device_name: Target device
            intent: Service intent to deploy
            dry_run: If True, only show what would change

        Returns:
            Deployment result
        """
        logger.info(f"[{device_name}] Deploying {intent.service_type} service")

        try:
            # Route to appropriate service deployer
            if intent.service_type == "bgp-peering":
                if intent.bgp_config is None:
                    return ServiceDeploymentResult(
                        device_name=device_name,
                        service_type=intent.service_type,
                        success=False,
                        message="BGP config missing",
                        changed=False,
                    )

                # Check if already configured (idempotency)
                if not dry_run:
                    already_configured = check_bgp_configured(
                        self.client, device_name, intent.bgp_config
                    )
                    if already_configured:
                        return ServiceDeploymentResult(
                            device_name=device_name,
                            service_type=intent.service_type,
                            success=True,
                            message="Already configured (no changes needed)",
                            changed=False,
                        )

                # Deploy service
                success, message = deploy_bgp_service(
                    self.client, device_name, intent.bgp_config, dry_run=dry_run
                )

                return ServiceDeploymentResult(
                    device_name=device_name,
                    service_type=intent.service_type,
                    success=success,
                    message=message,
                    changed=success and not dry_run,
                )

            # TODO: Add other service types
            # elif intent.service_type == "ospf":
            #     success, message = deploy_ospf_service(...)
            # elif intent.service_type == "static-routes":
            #     success, message = deploy_static_routes(...)

            else:
                return ServiceDeploymentResult(
                    device_name=device_name,
                    service_type=intent.service_type,
                    success=False,
                    message=f"Unsupported service type: {intent.service_type}",
                    changed=False,
                )

        except Exception as e:
            logger.error(f"[{device_name}] Exception during deployment: {e}")
            return ServiceDeploymentResult(
                device_name=device_name,
                service_type=intent.service_type,
                success=False,
                message=f"Exception: {e}",
                changed=False,
            )

    def deploy_service(
        self, intent: ServiceDeploymentIntent, dry_run: bool = False, parallel: bool = True
    ) -> list[ServiceDeploymentResult]:
        """
        Deploy service to all target devices.

        Args:
            intent: Service deployment intent
            dry_run: If True, only show what would change
            parallel: If True, deploy to devices in parallel

        Returns:
            List of deployment results for each device
        """
        logger.info("=" * 70)
        logger.info(
            f"{'[DRY-RUN] ' if dry_run else ''}Deploying {intent.service_type} "
            f"to {len(intent.target_devices)} device(s)"
        )
        logger.info("=" * 70)

        # Enrich target devices with inventory data if available
        if self.inventory:
            logger.debug("Enriching device list with inventory data")
            for device_name in intent.target_devices:
                device = self.inventory.get_device(device_name)
                if device:
                    logger.debug(
                        f"  - {device_name}: type={device.device_type}, "
                        f"groups={device.groups}"
                    )
                else:
                    logger.warning(
                        f"  - {device_name}: NOT FOUND in inventory (will attempt deployment anyway)"
                    )

        results = []

        if parallel and len(intent.target_devices) > 1:
            # Parallel deployment
            logger.info(f"Using parallel deployment (max_workers={self.max_workers})")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all deployment tasks
                future_to_device = {
                    executor.submit(self._deploy_to_device, device, intent, dry_run): device
                    for device in intent.target_devices
                }

                # Collect results as they complete
                for future in as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        result = future.result()
                        results.append(result)

                        status = "✓" if result.success else "✗"
                        changed_str = " (changed)" if result.changed else ""
                        logger.info(
                            f"{status} [{result.device_name}] {result.message}{changed_str}"
                        )

                    except Exception as e:
                        logger.error(f"✗ [{device}] Exception: {e}")
                        results.append(
                            ServiceDeploymentResult(
                                device_name=device,
                                service_type=intent.service_type,
                                success=False,
                                message=f"Executor exception: {e}",
                                changed=False,
                            )
                        )
        else:
            # Sequential deployment
            logger.info("Using sequential deployment")

            for device in intent.target_devices:
                result = self._deploy_to_device(device, intent, dry_run)
                results.append(result)

                status = "✓" if result.success else "✗"
                changed_str = " (changed)" if result.changed else ""
                logger.info(f"{status} [{result.device_name}] {result.message}{changed_str}")

        # Summary
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        changed_count = sum(1 for r in results if r.changed)

        logger.info("")
        logger.info("=" * 70)
        if dry_run:
            logger.info(f"DRY-RUN Complete: {success_count} would succeed, {failure_count} would fail")
        else:
            logger.info(
                f"Deployment complete: {success_count} succeeded ({changed_count} changed), "
                f"{failure_count} failed"
            )
        logger.info("=" * 70)

        return results

    def validate_service(
        self, intent: ServiceDeploymentIntent
    ) -> dict[str, dict[str, Any]]:
        """
        Validate service deployment across all devices.

        Args:
            intent: Service intent to validate

        Returns:
            Dict mapping device names to validation results
        """
        logger.info(
            f"Validating {intent.service_type} service on {len(intent.target_devices)} devices"
        )

        validation_results = {}

        for device in intent.target_devices:
            logger.info(f"[{device}] Running validation checks")

            # Sync device first
            self.client.sync_from_device(device)

            # Service-specific validation
            if intent.service_type == "bgp-peering":
                # Check BGP is configured
                config = self.client.get_device_config(device)
                if not config:
                    validation_results[device] = {
                        "valid": False,
                        "reason": "Could not retrieve config",
                    }
                    continue

                bgp_config = (
                    config.get("tailf-ncs:config", {})
                    .get("tailf-ned-cisco-ios:router", {})
                    .get("bgp", {})
                )

                if not bgp_config:
                    validation_results[device] = {
                        "valid": False,
                        "reason": "BGP not configured",
                    }
                    continue

                # Validate BGP AS and router ID
                current_as = bgp_config.get("as-no")
                current_router_id = bgp_config.get("bgp-router-id")

                if intent.bgp_config:
                    expected_as = intent.bgp_config.local_as
                    expected_router_id = intent.bgp_config.router_id

                    if str(current_as) != str(expected_as):
                        validation_results[device] = {
                            "valid": False,
                            "reason": f"BGP AS mismatch: expected {expected_as}, got {current_as}",
                            "bgp_as": current_as,
                        }
                        continue

                    if current_router_id != expected_router_id:
                        validation_results[device] = {
                            "valid": False,
                            "reason": f"Router ID mismatch: expected {expected_router_id}, got {current_router_id}",
                            "router_id": current_router_id,
                        }
                        continue

                # Basic validation passed
                validation_results[device] = {
                    "valid": True,
                    "bgp_as": current_as,
                    "router_id": current_router_id,
                }

            else:
                validation_results[device] = {
                    "valid": False,
                    "reason": f"Validation not implemented for {intent.service_type}",
                }

        # Summary
        valid_count = sum(1 for v in validation_results.values() if v.get("valid"))
        logger.info(
            f"Validation complete: {valid_count}/{len(intent.target_devices)} devices valid"
        )

        return validation_results

    def remove_service(
        self, intent: ServiceDeploymentIntent, dry_run: bool = False
    ) -> list[ServiceDeploymentResult]:
        """
        Remove service from all target devices.

        Args:
            intent: Service intent (identifies what to remove)
            dry_run: If True, only show what would be removed

        Returns:
            List of removal results
        """
        logger.warning("=" * 70)
        logger.warning(
            f"{'[DRY-RUN] ' if dry_run else ''}Removing {intent.service_type} "
            f"from {len(intent.target_devices)} device(s)"
        )
        logger.warning("=" * 70)

        results = []

        for device in intent.target_devices:
            try:
                if intent.service_type == "bgp-peering":
                    if intent.bgp_config is None:
                        results.append(
                            ServiceDeploymentResult(
                                device_name=device,
                                service_type=intent.service_type,
                                success=False,
                                message="BGP config missing",
                                changed=False,
                            )
                        )
                        continue

                    success, message = remove_bgp_service(
                        self.client, device, intent.bgp_config.local_as, dry_run=dry_run
                    )

                    results.append(
                        ServiceDeploymentResult(
                            device_name=device,
                            service_type=intent.service_type,
                            success=success,
                            message=message,
                            changed=success and not dry_run,
                        )
                    )

                else:
                    results.append(
                        ServiceDeploymentResult(
                            device_name=device,
                            service_type=intent.service_type,
                            success=False,
                            message=f"Removal not implemented for {intent.service_type}",
                            changed=False,
                        )
                    )

            except Exception as e:
                logger.error(f"[{device}] Exception during removal: {e}")
                results.append(
                    ServiceDeploymentResult(
                        device_name=device,
                        service_type=intent.service_type,
                        success=False,
                        message=f"Exception: {e}",
                        changed=False,
                    )
                )

        # Summary
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        changed_count = sum(1 for r in results if r.changed)

        logger.warning("")
        logger.warning("=" * 70)
        if dry_run:
            logger.warning(f"DRY-RUN Complete: {success_count} would be removed")
        else:
            logger.warning(
                f"Removal complete: {success_count} succeeded ({changed_count} changed), "
                f"{failure_count} failed"
            )
        logger.warning("=" * 70)

        return results

    def get_service_targets(
        self,
        group: str | None = None,
        device_type: str | None = None,
        **filters,
    ) -> list[str]:
        """
        Get device names from inventory matching filters.

        This is useful for dynamically building target_devices lists
        from inventory rather than hardcoding device names.

        Args:
            group: Filter by group name
            device_type: Filter by device type
            **filters: Additional filters

        Returns:
            List of device names

        Example:
            # Get all distribution routers for BGP deployment
            targets = orch.get_service_targets(group="distribution")

            # Get all IOS-XE devices in west region
            targets = orch.get_service_targets(device_type="ios-xe", region="west")
        """
        if not self.inventory:
            logger.warning(
                "No inventory loaded - cannot filter devices. "
                "Use explicit target_devices list instead."
            )
            return []

        devices = self.inventory.get_devices(
            group=group, device_type=device_type, **filters
        )

        device_names = [d.name for d in devices]

        logger.info(
            f"Inventory query returned {len(device_names)} devices "
            f"(group={group}, device_type={device_type}, filters={filters})"
        )

        return device_names


# Example usage
if __name__ == "__main__":
    from automation.inventory_loader import load_inventory
    from automation.service_models import (
        BGPNeighborIntent,
        BGPPeeringServiceIntent,
        ServiceDeploymentIntent,
    )

    # Load inventory
    inv = load_inventory()

    # Create NSO client
    with NSOClient(host="10.10.20.49") as client:
        # Create orchestrator with inventory
        orch = ServiceOrchestrator(client, inventory=inv, max_workers=5)

        # Get targets from inventory (distribution routers in west region)
        targets = orch.get_service_targets(group="distribution", region="west")
        print(f"Target devices: {targets}")

        # Create service intent
        intent = ServiceDeploymentIntent(
            service_type="bgp-peering",
            target_devices=targets,
            bgp_config=BGPPeeringServiceIntent(
                local_as=65001,
                router_id="10.100.100.1",
                neighbors=[
                    BGPNeighborIntent(
                        neighbor_ip="10.0.0.2",
                        remote_as=65002,
                        description="Core router",
                    )
                ],
            ),
        )

        # Deploy (dry-run)
        results = orch.deploy_service(intent, dry_run=True, parallel=True)

        # Show results
        for r in results:
            status = "✓" if r.success else "✗"
            print(f"{status} {r.device_name}: {r.message}")