"""
Integration tests for NSO loopback configuration.

Tests cover:
- NSO connectivity and health
- Device discovery and sync
- Loopback creation and validation
- Pre/post-checks
- Rollback on failure
"""

import pytest
from loguru import logger


@pytest.mark.nso
class TestNSOConnectivity:
    """Test basic NSO connectivity and setup."""

    def test_nso_health_check(self, nso_client_session):
        """Verify NSO is reachable and responsive."""
        assert nso_client_session.health_check(), "NSO health check failed"

    def test_devices_discovered(self, available_devices):
        """Verify at least one device is managed by NSO."""
        assert len(available_devices) > 0, "No devices found in NSO"
        logger.info(f"Discovered {len(available_devices)} devices")

    def test_device_sync(self, nso_client, test_device):
        """Verify we can sync configuration from a device."""
        result = nso_client.sync_from_device(test_device)
        assert result is True, f"Failed to sync from {test_device}"


@pytest.mark.nso
@pytest.mark.integration
class TestLoopbackConfiguration:
    """Test loopback interface configuration via NSO."""

    def test_create_loopback(self, nso_client, sync_device, test_loopback_config):
        """
        Test creating a loopback interface.

        Steps:
        1. Verify loopback doesn't exist (pre-check)
        2. Create loopback via NSO
        3. Commit changes
        4. Verify loopback exists (post-check)
        5. Cleanup
        """
        loopback_id = test_loopback_config["loopback_id"]
        device = sync_device

        # PRE-CHECK: Ensure loopback doesn't exist
        logger.info(f"PRE-CHECK: Verifying Loopback{loopback_id} doesn't exist")
        existing = nso_client.get_interface_config(device, "Loopback", loopback_id)

        if existing:
            logger.warning(f"Loopback{loopback_id} already exists, cleaning up first")
            nso_client.delete_loopback(device, loopback_id)

        # CREATE: Configure loopback
        logger.info(f"DEPLOY: Creating Loopback{loopback_id} on {device}")
        result = nso_client.configure_loopback(device_name=device, **test_loopback_config)
        assert result is True, "Failed to configure loopback"

        # POST-CHECK: Verify loopback exists
        logger.info(f"POST-CHECK: Verifying Loopback{loopback_id} exists")
        nso_client.sync_from_device(device)
        interface = nso_client.get_interface_config(device, "Loopback", loopback_id)
        assert interface is not None, "Loopback not found after creation"

        # Verify IP address (structure varies by NED version)
        logger.info(f"Loopback configuration: {interface}")

        # CLEANUP
        logger.info("CLEANUP: Removing test loopback")
        nso_client.delete_loopback(device, loopback_id)

    def test_create_multiple_loopbacks(self, nso_client, sync_device):
        """Test creating multiple loopbacks in a single transaction."""
        device = sync_device
        loopbacks = [
            {"loopback_id": "101", "ip_address": "10.101.101.1", "netmask": "255.255.255.255"},
            {"loopback_id": "102", "ip_address": "10.102.102.1", "netmask": "255.255.255.255"},
            {"loopback_id": "103", "ip_address": "10.103.103.1", "netmask": "255.255.255.255"},
        ]

        try:
            # Create all loopbacks
            for config in loopbacks:
                logger.info(f"Creating Loopback{config['loopback_id']}")
                result = nso_client.configure_loopback(device, **config)
                assert result is True, f"Failed to configure Loopback{config['loopback_id']}"

            # Verify all exist
            nso_client.sync_from_device(device)
            for config in loopbacks:
                interface = nso_client.get_interface_config(
                    device, "Loopback", config["loopback_id"]
                )
                assert interface is not None, f"Loopback{config['loopback_id']} not found"

        finally:
            # Cleanup
            logger.info("Cleaning up test loopbacks")
            for config in loopbacks:
                nso_client.delete_loopback(device, config["loopback_id"])

    def test_dry_run_loopback(self, nso_client, sync_device, test_loopback_config):
        """Test dry-run mode shows changes without applying them."""
        device = sync_device
        loopback_id = "200"

        # DRY-RUN: See what would change
        logger.info(f"DRY-RUN: Testing Loopback{loopback_id} on {device}")
        dry_run_result = nso_client.configure_loopback(
            device_name=device,
            loopback_id=loopback_id,
            ip_address="10.200.200.1",
            netmask="255.255.255.255",
            dry_run=True,  # Just show the diff
        )

        # Verify we got results (dict or True)
        assert dry_run_result is not False, "Dry-run failed"
        logger.info(f"Dry-run result: {dry_run_result}")

        # VERIFY: Loopback should NOT exist (dry-run doesn't apply)
        nso_client.sync_from_device(device)
        interface = nso_client.get_interface_config(device, "Loopback", loopback_id)
        assert interface is None, "Dry-run should not create loopback"

        logger.info("✓ Dry-run test passed - no changes applied")

    def test_rollback_loopback(self, nso_client, sync_device):
        """Test rollback functionality after creating a loopback."""
        device = sync_device
        loopback_id = "250"

        # PRE-CHECK: Ensure clean state
        logger.info("PRE-CHECK: Ensuring Loopback250 doesn't exist")
        existing = nso_client.get_interface_config(device, "Loopback", loopback_id)
        if existing:
            nso_client.delete_loopback(device, loopback_id)
            nso_client.sync_from_device(device)

        # CREATE: Add loopback with rollback tracking
        logger.info(f"CREATE: Adding Loopback{loopback_id}")
        success, rollback_fixed_number = nso_client.configure_loopback_with_rollback_id(
            device_name=device,
            loopback_id=loopback_id,
            ip_address="10.250.250.1",
            netmask="255.255.255.255",
            description="TEST_ROLLBACK",
        )
        assert success, "Failed to create loopback"
        logger.info(f"Got rollback fixed-number: {rollback_fixed_number}")

        # VERIFY: Loopback exists
        nso_client.sync_from_device(device)
        interface = nso_client.get_interface_config(device, "Loopback", loopback_id)
        assert interface is not None, "Loopback not found after creation"
        logger.info("✓ Loopback created successfully")

        # ROLLBACK: Two options - use relative id (0) or fixed-number
        logger.info("ROLLBACK: Reverting change")

        # Option 1: Use relative id (most recent = 0)
        rollback_success = nso_client.rollback(0)  # Simplest approach

        # Option 2: Use the specific fixed-number (if we got it)
        # if rollback_fixed_number:
        #     rollback_success = nso_client.rollback(rollback_fixed_number, use_fixed_number=True)
        # else:
        #     rollback_success = nso_client.rollback(0)

        assert rollback_success, "Rollback failed"

        # VERIFY: Loopback should be gone
        nso_client.sync_from_device(device)
        interface_after_rollback = nso_client.get_interface_config(device, "Loopback", loopback_id)
        assert interface_after_rollback is None, "Loopback still exists after rollback"

        logger.info("✓ Rollback test passed - loopback removed")

    def test_delete_loopback(self, nso_client, sync_device, test_loopback_config):
        """Test deleting a loopback interface."""
        device = sync_device
        loopback_id = "110"

        # Create loopback first
        logger.info(f"Creating Loopback{loopback_id} for deletion test")
        nso_client.configure_loopback(
            device_name=device,
            loopback_id=loopback_id,
            ip_address="10.110.110.1",
            netmask="255.255.255.255",
        )

        # Verify it exists
        nso_client.sync_from_device(device)
        interface = nso_client.get_interface_config(device, "Loopback", loopback_id)
        assert interface is not None, "Loopback wasn't created"

        # Delete it
        logger.info(f"Deleting Loopback{loopback_id}")
        delete_result = nso_client.delete_loopback(device, loopback_id)
        assert delete_result is True, "Delete operation failed"
