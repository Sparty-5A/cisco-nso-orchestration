"""Tests for device-level BGP deployment via device_engine."""

import pytest
from loguru import logger

from automation.device_engine import DeviceEngine
from automation.device_models import (
    BGPIntent,
    BGPNeighborIntent,
    DeviceIntent,
    NetworkIntent,
)


@pytest.mark.nso
@pytest.mark.integration
class TestDeviceLevelBGP:
    """Test BGP deployment using device-level intent pattern."""

    def test_calculate_bgp_changes_not_configured(
        self, nso_client, sync_device, inventory
    ):
        """Test calculating BGP changes when BGP is not configured."""
        device = sync_device

        # Create device intent with BGP
        device_intent = DeviceIntent(
            name=device,
            device_type="ios-xe",
            bgp=BGPIntent(
                asn=65099,
                router_id="10.99.99.1",
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.99",
                        remote_asn=65100,
                        description="Test neighbor",
                        update_source="Loopback0",
                    )
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[device_intent])

        # Create engine and calculate changes
        engine = DeviceEngine(nso_client, inventory=inventory)
        changes = engine.calculate_bgp_changes(device_intent)

        # Should have one change (create BGP)
        assert len(changes) == 1
        assert changes[0].action == "create"
        assert changes[0].resource_type == "bgp"
        assert changes[0].device == device

    def test_apply_device_bgp_dry_run(self, nso_client, sync_device, inventory):
        """Test applying device-level BGP in dry-run mode."""
        device = sync_device

        device_intent = DeviceIntent(
            name=device,
            device_type="ios-xe",
            bgp=BGPIntent(
                asn=65098,
                router_id="10.98.98.1",
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.98",
                        remote_asn=65099,
                        description="Dry-run test",
                    )
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[device_intent])

        # Apply in dry-run mode
        engine = DeviceEngine(nso_client, inventory=inventory)
        success_count, failure_count = engine.apply_intent(
            network_intent, dry_run=True
        )

        # Dry-run should succeed
        assert success_count >= 0
        assert failure_count == 0

    def test_deploy_device_bgp_full_cycle(self, nso_client, sync_device, inventory):
        """Test full BGP deployment cycle: deploy, verify, remove."""
        device = sync_device

        device_intent = DeviceIntent(
            name=device,
            device_type="ios-xe",
            bgp=BGPIntent(
                asn=65097,
                router_id="10.97.97.1",
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.97",
                        remote_asn=65098,
                        description="Device-level BGP test",
                        update_source="Loopback0",
                    )
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[device_intent])
        engine = DeviceEngine(nso_client, inventory=inventory)

        try:
            # DEPLOY
            logger.info(f"Deploying BGP to {device} via device engine")
            success_count, failure_count = engine.apply_intent(
                network_intent, dry_run=False
            )

            assert failure_count == 0, "BGP deployment failed"
            assert success_count > 0, "No changes applied"
            logger.info("✓ BGP deployed successfully")

            # VERIFY - Calculate changes again (should be none)
            logger.info(f"Verifying BGP is configured on {device}")
            changes = engine.calculate_bgp_changes(device_intent)
            assert len(changes) == 0, "BGP not configured correctly"
            logger.info("✓ BGP verified (no further changes needed)")

            # TEST IDEMPOTENCY - Apply again
            logger.info("Testing idempotency")
            success_count, failure_count = engine.apply_intent(
                network_intent, dry_run=False
            )

            # Should be no changes on second run
            assert success_count == 0, "Should be no changes on idempotent run"
            logger.info("✓ Idempotency check passed")

        finally:
            # CLEANUP
            logger.info(f"Removing BGP from {device}")
            from services.bgp_peering import remove_bgp_service

            success, message = remove_bgp_service(
                nso_client, device, 65097, dry_run=False
            )
            if success:
                logger.info(f"✓ Cleanup successful: {message}")

    def test_deploy_bgp_to_multiple_devices(
        self, nso_client, available_devices, inventory
    ):
        """Test deploying BGP to multiple devices."""
        # Get two IOS-XE devices if available
        xe_devices = [
            d
            for d in available_devices
            if any(
                keyword in d.lower()
                for keyword in ["dist-rtr", "internet-rtr", "dev-dist"]
            )
        ]

        if len(xe_devices) < 2:
            pytest.skip("Need at least 2 IOS-XE devices for multi-device test")

        device1 = xe_devices[0]
        device2 = xe_devices[1]

        # Create intent for both devices with unique configs
        network_intent = NetworkIntent(
            devices=[
                DeviceIntent(
                    name=device1,
                    device_type="ios-xe",
                    bgp=BGPIntent(
                        asn=65096,
                        router_id="10.96.96.1",
                        neighbors=[
                            BGPNeighborIntent(
                                ip="10.96.96.2",
                                remote_asn=65096,
                                description=f"To {device2}",
                            )
                        ],
                    ),
                ),
                DeviceIntent(
                    name=device2,
                    device_type="ios-xe",
                    bgp=BGPIntent(
                        asn=65096,
                        router_id="10.96.96.2",
                        neighbors=[
                            BGPNeighborIntent(
                                ip="10.96.96.1",
                                remote_asn=65096,
                                description=f"To {device1}",
                            )
                        ],
                    ),
                ),
            ]
        )

        engine = DeviceEngine(nso_client, inventory=inventory)

        try:
            # Deploy to both devices
            logger.info(f"Deploying BGP to {device1} and {device2}")
            success_count, failure_count = engine.apply_intent(
                network_intent, dry_run=False
            )

            assert failure_count == 0, "Multi-device BGP deployment failed"
            logger.info(f"✓ BGP deployed to {success_count} devices")

        finally:
            # Cleanup
            from services.bgp_peering import remove_bgp_service

            for device in [device1, device2]:
                remove_bgp_service(nso_client, device, 65096, dry_run=False)

    def test_device_bgp_with_loopbacks(self, nso_client, sync_device, inventory):
        """Test deploying both loopbacks and BGP together (integrated)."""
        from automation.device_models import LoopbackIntent

        device = sync_device

        # Create intent with BOTH loopbacks and BGP
        device_intent = DeviceIntent(
            name=device,
            device_type="ios-xe",
            loopbacks=[
                LoopbackIntent(
                    id=150,
                    ipv4="10.150.150.1",
                    netmask="255.255.255.255",
                    description="BGP loopback",
                )
            ],
            bgp=BGPIntent(
                asn=65095,
                router_id="10.150.150.1",  # Using the loopback we created
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.95",
                        remote_asn=65096,
                        description="Integrated test",
                        update_source="Loopback150",
                    )
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[device_intent])
        engine = DeviceEngine(nso_client, inventory=inventory)

        try:
            # Deploy both loopback and BGP in one operation
            logger.info(f"Deploying loopback + BGP to {device}")
            success_count, failure_count = engine.apply_intent(
                network_intent, dry_run=False
            )

            assert failure_count == 0, "Integrated deployment failed"
            assert success_count >= 2, "Should have at least 2 changes (loopback + BGP)"
            logger.info("✓ Loopback + BGP deployed together successfully")

        finally:
            # Cleanup both
            from services.bgp_peering import remove_bgp_service

            remove_bgp_service(nso_client, device, 65095, dry_run=False)
            nso_client.delete_loopback(device, "150")


@pytest.mark.unit
def test_device_intent_with_bgp_validation():
    """Test device intent model validation with BGP."""
    # Valid device intent with BGP
    device = DeviceIntent(
        name="test-rtr",
        device_type="ios-xe",
        bgp=BGPIntent(
            asn=65001,
            router_id="10.1.1.1",
            neighbors=[
                BGPNeighborIntent(
                    ip="10.0.0.2",
                    remote_asn=65002,
                    description="Test neighbor",
                )
            ],
        ),
    )

    assert device.name == "test-rtr"
    assert device.bgp is not None
    assert device.bgp.asn == 65001
    assert len(device.bgp.neighbors) == 1

    # Device without BGP is valid too
    device_no_bgp = DeviceIntent(
        name="test-rtr2",
        device_type="ios-xe",
        loopbacks=[],
    )

    assert device_no_bgp.bgp is None


@pytest.mark.unit
def test_network_intent_with_mixed_devices():
    """Test network intent with some devices having BGP and some not."""
    intent = NetworkIntent(
        devices=[
            DeviceIntent(
                name="rtr1",
                device_type="ios-xe",
                bgp=BGPIntent(
                    asn=65001,
                    router_id="10.1.1.1",
                    neighbors=[
                        BGPNeighborIntent(ip="10.0.0.2", remote_asn=65002)
                    ],
                ),
            ),
            DeviceIntent(
                name="rtr2",
                device_type="ios-xe",
                # No BGP on this device
                loopbacks=[],
            ),
            DeviceIntent(
                name="rtr3",
                device_type="ios-xr",
                bgp=BGPIntent(
                    asn=65003,
                    router_id="10.3.3.3",
                    neighbors=[],
                ),
            ),
        ]
    )

    assert len(intent.devices) == 3
    assert intent.devices[0].bgp is not None
    assert intent.devices[1].bgp is None  # No BGP
    assert intent.devices[2].bgp is not None


@pytest.mark.nso
@pytest.mark.integration
class TestBGPNeighborDeletion:
    """Test BGP neighbor deletion behavior (safe vs strict mode)."""

    def test_safe_mode_leaves_extra_neighbors(
        self, nso_client, sync_device, inventory
    ):
        """Test that safe mode (default) leaves unmanaged neighbors alone."""
        device = sync_device

        # Step 1: Deploy BGP with 2 neighbors
        intent_with_two = DeviceIntent(
            name=device,
            device_type="ios-xe",
            delete_unmanaged_bgp_neighbors=False,  # Safe mode
            bgp=BGPIntent(
                asn=65094,
                router_id="10.94.94.1",
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.94",
                        remote_asn=65095,
                        description="Neighbor 1",
                    ),
                    BGPNeighborIntent(
                        ip="10.0.0.95",
                        remote_asn=65095,
                        description="Neighbor 2",
                    ),
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[intent_with_two])
        engine = DeviceEngine(nso_client, inventory=inventory)

        try:
            # Deploy with 2 neighbors
            logger.info("Deploying BGP with 2 neighbors")
            success, failure = engine.apply_intent(network_intent, dry_run=False)
            assert failure == 0

            # Step 2: Update intent to only have 1 neighbor (remove one from intent)
            intent_with_one = DeviceIntent(
                name=device,
                device_type="ios-xe",
                delete_unmanaged_bgp_neighbors=False,  # Safe mode - don't delete
                bgp=BGPIntent(
                    asn=65094,
                    router_id="10.94.94.1",
                    neighbors=[
                        BGPNeighborIntent(
                            ip="10.0.0.94",
                            remote_asn=65095,
                            description="Neighbor 1",
                        ),
                        # Neighbor 2 removed from intent!
                    ],
                ),
            )

            network_intent2 = NetworkIntent(devices=[intent_with_one])

            # Apply updated intent (safe mode should leave neighbor 2 alone)
            logger.info("Applying updated intent (safe mode)")
            success, failure = engine.apply_intent(network_intent2, dry_run=False)

            # Should be no changes (BGP already configured, safe mode ignores extra)
            assert success == 0  # No changes applied

            # Verify neighbor 2 still exists
            nso_client.sync_from_device(device)
            config = nso_client.get_device_config(device)
            bgp_config = (
                config.get("tailf-ncs:config", {})
                .get("tailf-ned-cisco-ios:router", {})
                .get("bgp", {})
            )

            neighbors = bgp_config.get("neighbor", [])
            if not isinstance(neighbors, list):
                neighbors = [neighbors]

            neighbor_ips = {n.get("id") for n in neighbors}
            assert "10.0.0.94" in neighbor_ips  # Still there
            assert "10.0.0.95" in neighbor_ips  # ✓ Still there (safe mode!)

            logger.info("✓ Safe mode test passed - extra neighbor preserved")

        finally:
            from services.bgp_peering import remove_bgp_service

            remove_bgp_service(nso_client, device, 65094, dry_run=False)

    def test_strict_mode_deletes_extra_neighbors(
        self, nso_client, sync_device, inventory
    ):
        """Test that strict mode deletes unmanaged neighbors."""
        device = sync_device

        # Step 1: Deploy BGP with 2 neighbors
        intent_with_two = DeviceIntent(
            name=device,
            device_type="ios-xe",
            delete_unmanaged_bgp_neighbors=False,
            bgp=BGPIntent(
                asn=65093,
                router_id="10.93.93.1",
                neighbors=[
                    BGPNeighborIntent(
                        ip="10.0.0.93",
                        remote_asn=65094,
                        description="Neighbor 1",
                    ),
                    BGPNeighborIntent(
                        ip="10.0.0.92",
                        remote_asn=65094,
                        description="Neighbor 2",
                    ),
                ],
            ),
        )

        network_intent = NetworkIntent(devices=[intent_with_two])
        engine = DeviceEngine(nso_client, inventory=inventory)

        try:
            # Deploy with 2 neighbors
            logger.info("Deploying BGP with 2 neighbors")
            success, failure = engine.apply_intent(network_intent, dry_run=False)
            assert failure == 0

            # Verify both neighbors exist
            nso_client.sync_from_device(device)
            config = nso_client.get_device_config(device)
            bgp_config = (
                config.get("tailf-ncs:config", {})
                .get("tailf-ned-cisco-ios:router", {})
                .get("bgp", {})
            )

            neighbors = bgp_config.get("neighbor", [])
            if not isinstance(neighbors, list):
                neighbors = [neighbors]

            assert len(neighbors) == 2

            # Step 2: Update intent with strict mode enabled
            intent_with_one_strict = DeviceIntent(
                name=device,
                device_type="ios-xe",
                delete_unmanaged_bgp_neighbors=True,  # ⚠️ Strict mode!
                bgp=BGPIntent(
                    asn=65093,
                    router_id="10.93.93.1",
                    neighbors=[
                        BGPNeighborIntent(
                            ip="10.0.0.93",
                            remote_asn=65094,
                            description="Neighbor 1",
                        ),
                        # Neighbor 2 removed from intent + strict mode = DELETE!
                    ],
                ),
            )

            network_intent2 = NetworkIntent(devices=[intent_with_one_strict])

            # Apply with strict mode
            logger.info("Applying updated intent (strict mode)")
            success, failure = engine.apply_intent(network_intent2, dry_run=False)

            # Should have 1 deletion
            assert success == 1  # One neighbor deleted
            assert failure == 0

            # Verify neighbor 2 is gone
            nso_client.sync_from_device(device)
            config = nso_client.get_device_config(device)
            bgp_config = (
                config.get("tailf-ncs:config", {})
                .get("tailf-ned-cisco-ios:router", {})
                .get("bgp", {})
            )

            neighbors = bgp_config.get("neighbor", [])
            if not isinstance(neighbors, list):
                neighbors = [neighbors] if neighbors else []

            neighbor_ips = {n.get("id") for n in neighbors}
            assert "10.0.0.93" in neighbor_ips  # Still there
            assert "10.0.0.92" not in neighbor_ips  # ✓ Deleted (strict mode!)

            logger.info("✓ Strict mode test passed - extra neighbor removed")

        finally:
            from services.bgp_peering import remove_bgp_service

            remove_bgp_service(nso_client, device, 65093, dry_run=False)


@pytest.mark.unit
def test_device_intent_deletion_flags():
    """Test that deletion flags work correctly in device intent."""
    # Test defaults (both should be False)
    device1 = DeviceIntent(
        name="test-rtr",
        device_type="ios-xe",
    )
    assert device1.delete_unmanaged_loopbacks is False
    assert device1.delete_unmanaged_bgp_neighbors is False

    # Test explicit settings
    device2 = DeviceIntent(
        name="test-rtr2",
        device_type="ios-xe",
        delete_unmanaged_loopbacks=True,
        delete_unmanaged_bgp_neighbors=True,
    )
    assert device2.delete_unmanaged_loopbacks is True
    assert device2.delete_unmanaged_bgp_neighbors is True

    # Test mixed settings
    device3 = DeviceIntent(
        name="test-rtr3",
        device_type="ios-xe",
        delete_unmanaged_loopbacks=True,  # Strict for loopbacks
        delete_unmanaged_bgp_neighbors=False,  # Safe for BGP
    )
    assert device3.delete_unmanaged_loopbacks is True
    assert device3.delete_unmanaged_bgp_neighbors is False