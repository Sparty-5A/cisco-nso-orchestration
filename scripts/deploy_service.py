#!/usr/bin/env python3
"""
Deploy network services to devices via NSO.

This CLI tool deploys service-level configurations (BGP, OSPF, L3VPN)
to one or more devices using the service orchestrator with inventory integration.
"""

import json
import sys
from pathlib import Path

import yaml
from decouple import config
from loguru import logger

from nso_orchestration.automation.inventory_loader import load_inventory
from nso_orchestration.automation.nso_client import NSOClient
from nso_orchestration.automation.service_models import ServiceDeploymentIntent
from nso_orchestration.automation.service_orchestrator import ServiceOrchestrator


def load_service_intent(file_path: Path) -> ServiceDeploymentIntent:
    """
    Load and validate service intent from YAML file.

    Args:
        file_path: Path to service intent file

    Returns:
        Validated ServiceDeploymentIntent

    Raises:
        ValidationError: If intent is invalid
    """
    logger.info(f"Loading service intent from {file_path}")

    with open(file_path) as f:
        intent_data = yaml.safe_load(f)

    # Validate with Pydantic
    intent = ServiceDeploymentIntent(**intent_data)

    logger.info(
        f"✓ Intent validated: {intent.service_type} → "
        f"{len(intent.target_devices)} device(s)"
    )

    return intent


def main():
    """Main CLI logic."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy network services via NSO with inventory integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy BGP service (dry-run first!)
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --dry-run

  # Deploy BGP service (apply changes)
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml

  # Deploy with validation
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --validate

  # Deploy to devices from inventory (filter by group)
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --group distribution

  # Deploy sequentially (no parallelism)
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --no-parallel

  # Remove service
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --remove

  # JSON output for automation
  python scripts/deploy_service.py --intent intent/service_bgp_peering.yaml --json
        """,
    )

    parser.add_argument(
        "--intent",
        type=Path,
        required=True,
        help="Path to service intent YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate service after deployment",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove service instead of deploying",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Deploy sequentially (disable parallelism)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Max parallel workers (default: 5)",
    )
    parser.add_argument(
        "--group",
        type=str,
        help="Override target devices with inventory group filter",
    )
    parser.add_argument(
        "--device-type",
        type=str,
        help="Override target devices with device type filter (ios-xe, ios-xr)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )

    args = parser.parse_args()

    # Resolve intent file path
    intent_file = args.intent
    if not intent_file.is_absolute():
        # Check if file exists relative to current directory first
        if intent_file.exists():
            intent_file = intent_file.resolve()
        else:
            # Try relative to script directory
            script_dir = Path(__file__).parent.parent
            intent_file = script_dir / intent_file

    if not intent_file.exists():
        logger.error(f"Intent file not found: {intent_file}")
        return 1

    try:
        # Load intent
        intent = load_service_intent(intent_file)

        # Load inventory
        logger.info("Loading device inventory")
        inventory = load_inventory()

        # Validate inventory
        is_valid, issues = inventory.validate()
        if not is_valid:
            logger.warning("Inventory has validation issues:")
            for issue in issues:
                logger.warning(f"  - {issue}")
            logger.warning("Continuing anyway...")

        # Override target devices from inventory if filters provided
        if args.group or args.device_type:
            logger.info(
                f"Overriding target devices from inventory "
                f"(group={args.group}, device_type={args.device_type})"
            )
            filtered_devices = inventory.get_device_names(
                group=args.group, device_type=args.device_type
            )

            if not filtered_devices:
                logger.error(
                    f"No devices found in inventory matching filters "
                    f"(group={args.group}, device_type={args.device_type})"
                )
                return 1

            logger.info(f"Using {len(filtered_devices)} devices from inventory: {filtered_devices}")
            intent.target_devices = filtered_devices

        # Connect to NSO
        nso_host = config("NSO_HOST", default="10.10.20.49")
        logger.info(f"Connecting to NSO at {nso_host}")

        with NSOClient(host=nso_host) as client:
            # Health check
            if not client.health_check():
                logger.error("NSO health check failed")
                return 1

            # Create orchestrator with inventory
            orchestrator = ServiceOrchestrator(
                nso_client=client, inventory=inventory, max_workers=args.max_workers
            )

            # Execute action
            if args.remove:
                # Remove service
                results = orchestrator.remove_service(intent, dry_run=args.dry_run)

            else:
                # Deploy service
                results = orchestrator.deploy_service(
                    intent, dry_run=args.dry_run, parallel=not args.no_parallel
                )

                # Validate if requested
                if args.validate and not args.dry_run:
                    logger.info("")
                    validation = orchestrator.validate_service(intent)

                    for device, result in validation.items():
                        status = "✓" if result.get("valid") else "✗"
                        reason = result.get("reason", "")
                        logger.info(f"{status} [{device}] {reason or 'Valid'}")

            # Output results
            if args.json:
                output = {
                    "action": "remove" if args.remove else "deploy",
                    "dry_run": args.dry_run,
                    "intent_file": str(intent_file),
                    "service_type": intent.service_type,
                    "target_devices": intent.target_devices,
                    "results": [
                        {
                            "device": r.device_name,
                            "success": r.success,
                            "message": r.message,
                            "changed": r.changed,
                        }
                        for r in results
                    ],
                    "summary": {
                        "total": len(results),
                        "succeeded": sum(1 for r in results if r.success),
                        "failed": sum(1 for r in results if not r.success),
                        "changed": sum(1 for r in results if r.changed),
                    },
                }
                print(json.dumps(output, indent=2))

            # Exit code
            failed_count = sum(1 for r in results if not r.success)
            return 0 if failed_count == 0 else 1

    except Exception as e:
        logger.exception(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())