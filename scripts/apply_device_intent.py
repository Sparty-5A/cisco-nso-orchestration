#!/usr/bin/env python3
"""
Apply device-level intent to network devices.

This script loads device intent from YAML and reconciles it with the
actual device state using the device engine.

Supports:
- Loopback interfaces
- BGP configuration
- Per-device deletion policies

Usage:
    # Dry-run (show changes without applying)
    python scripts/apply_device_intent.py --intent intent/device_loopbacks.yaml --dry-run

    # Apply loopback configuration
    python scripts/apply_device_intent.py --intent intent/device_loopbacks.yaml

    # Apply BGP configuration
    python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml

    # Apply both loopbacks and BGP
    python scripts/apply_device_intent.py --intent intent/device_loopbacks.yaml --intent intent/device_bgp_configs.yaml

    # Filter by device
    python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml --device dist-rtr01

    # Verbose output
    python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml --verbose
"""

import argparse
import sys
from pathlib import Path

import yaml
from decouple import config
from loguru import logger

from automation.device_engine import DeviceEngine
from automation.device_models import NetworkIntent
from automation.inventory_loader import load_inventory
from automation.nso_client import NSOClient


def load_device_intent(intent_file: Path) -> NetworkIntent:
    """
    Load device intent from YAML file.

    Args:
        intent_file: Path to intent YAML file

    Returns:
        NetworkIntent object

    Raises:
        FileNotFoundError: If intent file doesn't exist
        ValidationError: If intent validation fails
    """
    if not intent_file.exists():
        logger.error(f"Intent file not found: {intent_file}")
        raise FileNotFoundError(f"Intent file not found: {intent_file}")

    logger.info(f"Loading intent from: {intent_file}")

    with open(intent_file) as f:
        intent_data = yaml.safe_load(f)

    # Validate intent using Pydantic model
    try:
        intent = NetworkIntent(**intent_data)
        logger.info(
            f"✓ Intent loaded successfully: {len(intent.devices)} device(s)"
        )
        return intent
    except Exception as e:
        logger.error(f"Intent validation failed: {e}")
        raise


def merge_intents(intents: list[NetworkIntent]) -> NetworkIntent:
    """
    Merge multiple intent files into a single NetworkIntent.

    If the same device appears in multiple intents, merge their configurations:
    - Loopbacks are combined (duplicates by ID are kept from last definition)
    - BGP uses the last definition
    - Deletion flags use the last definition

    Args:
        intents: List of NetworkIntent objects

    Returns:
        Merged NetworkIntent
    """
    if len(intents) == 1:
        return intents[0]

    logger.info(f"Merging {len(intents)} intent files")

    # Use dict to handle duplicates - merge configs instead of replacing
    device_map = {}

    for intent in intents:
        for device in intent.devices:
            if device.name in device_map:
                logger.info(
                    f"Device '{device.name}' appears in multiple intents, merging configurations"
                )

                existing = device_map[device.name]

                # Merge loopbacks (combine lists, last wins for duplicates by ID)
                merged_loopbacks = list(existing.loopbacks)
                existing_lb_ids = {lb.id for lb in existing.loopbacks}

                for new_lb in device.loopbacks:
                    if new_lb.id in existing_lb_ids:
                        # Replace existing loopback with new definition
                        merged_loopbacks = [lb for lb in merged_loopbacks if lb.id != new_lb.id]
                        merged_loopbacks.append(new_lb)
                        logger.debug(f"  - Updated Loopback{new_lb.id}")
                    else:
                        # Add new loopback
                        merged_loopbacks.append(new_lb)
                        logger.debug(f"  - Added Loopback{new_lb.id}")

                # BGP: use the latest definition if provided
                merged_bgp = device.bgp if device.bgp is not None else existing.bgp
                if device.bgp is not None and existing.bgp is not None:
                    logger.debug(f"  - Replaced BGP config")
                elif device.bgp is not None:
                    logger.debug(f"  - Added BGP config")

                # Deletion flags: use latest (non-default takes precedence)
                merged_delete_loopbacks = device.delete_unmanaged_loopbacks
                merged_delete_bgp_neighbors = device.delete_unmanaged_bgp_neighbors

                # Create merged device
                from automation.device_models import DeviceIntent
                merged_device = DeviceIntent(
                    name=device.name,
                    device_type=device.device_type,
                    loopbacks=merged_loopbacks,
                    bgp=merged_bgp,
                    delete_unmanaged_loopbacks=merged_delete_loopbacks,
                    delete_unmanaged_bgp_neighbors=merged_delete_bgp_neighbors,
                )

                device_map[device.name] = merged_device
            else:
                # First occurrence of this device
                device_map[device.name] = device

    merged = NetworkIntent(devices=list(device_map.values()))
    logger.info(f"✓ Merged into {len(merged.devices)} unique device(s)")

    return merged


def filter_intent_by_device(
        intent: NetworkIntent, device_name: str
) -> NetworkIntent:
    """
    Filter intent to only include a specific device.

    Args:
        intent: Full intent
        device_name: Device to filter for

    Returns:
        Filtered intent with only the specified device
    """
    device = intent.get_device(device_name)

    if not device:
        logger.error(f"Device '{device_name}' not found in intent")
        raise ValueError(f"Device '{device_name}' not found in intent")

    logger.info(f"Filtered intent to device: {device_name}")
    return NetworkIntent(devices=[device])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply device-level intent to network devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run (show what would change)
  %(prog)s --intent intent/device_loopbacks.yaml --dry-run

  # Apply loopbacks
  %(prog)s --intent intent/device_loopbacks.yaml

  # Apply BGP
  %(prog)s --intent intent/device_bgp_configs.yaml

  # Apply both (merge multiple intent files)
  %(prog)s --intent intent/device_loopbacks.yaml --intent intent/device_bgp_configs.yaml

  # Apply to specific device only
  %(prog)s --intent intent/device_bgp_configs.yaml --device dist-rtr01

  # Verbose logging
  %(prog)s --intent intent/device_bgp_configs.yaml --verbose
        """,
    )

    parser.add_argument(
        "--intent",
        "-i",
        action="append",
        required=True,
        help="Path to device intent YAML file (can specify multiple times)",
    )

    parser.add_argument(
        "--device",
        "-d",
        help="Apply intent to specific device only (filter)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without applying",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--nso-host",
        default=config("NSO_HOST", default="10.10.20.49"),
        help="NSO host (default: from env or 10.10.20.49)",
    )

    parser.add_argument(
        "--nso-port",
        type=int,
        default=config("NSO_PORT", default=8080, cast=int),
        help="NSO port (default: from env or 8080)",
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()  # Remove default handler
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.add(
        sys.stderr, level=log_level, format="<level>{message}</level>", colorize=True
    )

    # Load intent file(s)
    intents = []
    for intent_path in args.intent:
        try:
            intent = load_device_intent(Path(intent_path))
            intents.append(intent)
        except Exception as e:
            logger.error(f"Failed to load intent: {e}")
            return 1

    # Merge intents if multiple files provided
    merged_intent = merge_intents(intents)

    # Filter by device if specified
    if args.device:
        try:
            merged_intent = filter_intent_by_device(merged_intent, args.device)
        except ValueError as e:
            logger.error(str(e))
            return 1

    # Show intent summary
    logger.info("=" * 70)
    logger.info("Device Intent Summary")
    logger.info("=" * 70)
    for device in merged_intent.devices:
        logger.info(f"Device: {device.name} ({device.device_type})")
        if device.loopbacks:
            logger.info(f"  Loopbacks: {len(device.loopbacks)}")
            for lb in device.loopbacks:
                logger.info(f"    - Lo{lb.id}: {lb.ipv4}/{lb.netmask}")
        if device.bgp:
            logger.info(f"  BGP:")
            logger.info(f"    - AS: {device.bgp.asn}")
            logger.info(f"    - Router-ID: {device.bgp.router_id}")
            logger.info(f"    - Neighbors: {len(device.bgp.neighbors)}")
            for neighbor in device.bgp.neighbors:
                logger.info(f"      - {neighbor.ip} (AS {neighbor.remote_asn})")
        logger.info(
            f"  Delete unmanaged loopbacks: {device.delete_unmanaged_loopbacks}"
        )
    logger.info("=" * 70)

    # Initialize NSO client
    logger.info(f"Connecting to NSO at {args.nso_host}:{args.nso_port}")
    nso_client = NSOClient(
        host=args.nso_host,
        port=args.nso_port,
        username=config("NSO_USER", default="developer"),
        password=config("NSO_PW", default="C1sco12345"),
    )

    # Health check
    if not nso_client.health_check():
        logger.error("NSO health check failed - cannot proceed")
        return 1

    # Load inventory (for device metadata, especially for BGP)
    try:
        logger.info("Loading inventory for device metadata")
        inventory = load_inventory()
    except Exception as e:
        logger.warning(f"Could not load inventory: {e}")
        logger.warning("Continuing without inventory (may affect BGP deployment)")
        inventory = None

    # Initialize device engine
    engine = DeviceEngine(nso_client, inventory=inventory)

    # Apply intent
    try:
        success_count, failure_count = engine.apply_intent(
            merged_intent, dry_run=args.dry_run
        )

        # Summary
        if args.dry_run:
            logger.info(
                f"\n✓ Dry-run complete: {success_count} changes would be applied"
            )
            return 0
        else:
            if failure_count > 0:
                logger.error(
                    f"\n✗ Intent application completed with errors: "
                    f"{success_count} succeeded, {failure_count} failed"
                )
                return 1
            else:
                logger.info(
                    f"\n✓ Intent application successful: {success_count} changes applied"
                )
                return 0

    except Exception as e:
        logger.error(f"Intent application failed: {e}")
        if args.verbose:
            logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    sys.exit(main())