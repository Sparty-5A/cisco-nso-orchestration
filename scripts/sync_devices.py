#!/usr/bin/env python3
"""
Sync all devices from NSO.

This should be run after reserving the NSO sandbox to ensure
NSO's CDB has the latest device configurations.
"""
from decouple import config
from loguru import logger

from nso_orchestration.automation.nso_client import NSOClient


def main():
    """Sync all devices from NSO."""
    host = config("NSO_HOST", default="10.10.20.49")

    logger.info(f"Connecting to NSO at {host}")

    with NSOClient(host=host) as client:
        # Health check (just verifies NSO is reachable)
        if not client.health_check():
            logger.error("NSO is not reachable - check VPN and host")
            return 1

        # Get devices
        devices = client.get_devices()
        if not devices:
            logger.error("No devices found in NSO")
            return 1

        logger.info(f"Found {len(devices)} devices to sync")

        # Sync each device
        success_count = 0
        fail_count = 0

        for device in devices:
            logger.info(f"Syncing {device}...")
            if client.sync_from_device(device):
                success_count += 1
            else:
                fail_count += 1

        # Summary
        logger.info("=" * 60)
        logger.info(f"Sync complete: {success_count} succeeded, {fail_count} failed")
        logger.info("=" * 60)

        return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    exit(main())
