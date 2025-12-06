"""Tests for BGP service deployment."""

import pytest
from loguru import logger

from nso_orchestration.automation.service_models import (
    BGPNeighborIntent,
    BGPPeeringServiceIntent,
)
from nso_orchestration.services.bgp_peering import (
    check_bgp_configured,
    deploy_bgp_service,
    remove_bgp_service,
)


@pytest.mark.nso
@pytest.mark.integration
class TestBGPServiceDeployment:
    """Test BGP service deployment functionality."""

    def test_deploy_bgp_dry_run(self, nso_client, test_device):
        """Test BGP service deployment in dry-run mode."""
        intent = BGPPeeringServiceIntent(
            local_as=65099,
            router_id="10.99.99.1",
            neighbors=[
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.99",
                    remote_as=65100,
                    description="Test neighbor (dry-run)",
                )
            ],
        )

        # Deploy in dry-run mode
        success, message = deploy_bgp_service(
            nso_client, test_device, intent, dry_run=True
        )

        # Dry-run should succeed
        assert "DRY-RUN" in message
        logger.info(f"Dry-run result: {message}")

        # Verify artifact was created
        from pathlib import Path

        artifact_file = Path("artifacts") / f"{test_device}_bgp_service.xml"
        if artifact_file.exists():
            logger.info(f"✓ Artifact created: {artifact_file}")
            content = artifact_file.read_text()
            assert "65099" in content
            assert "10.99.99.1" in content
            assert "10.0.0.99" in content

    def test_check_bgp_configured_not_exists(self, nso_client, test_device):
        """Test checking BGP when it doesn't exist."""
        intent = BGPPeeringServiceIntent(
            local_as=65098,  # Unlikely to exist
            router_id="10.98.98.1",
            neighbors=[
                BGPNeighborIntent(neighbor_ip="10.0.0.98", remote_as=65099)
            ],
        )

        # Should return False (not configured)
        is_configured = check_bgp_configured(nso_client, test_device, intent)
        assert is_configured is False

    def test_deploy_and_remove_bgp(self, nso_client, sync_device):
        """Test full BGP deployment and removal cycle."""
        device = sync_device

        intent = BGPPeeringServiceIntent(
            local_as=65097,
            router_id="10.97.97.1",
            neighbors=[
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.97",
                    remote_as=65098,
                    description="Test BGP neighbor",
                    password="TestPassword123",
                )
            ],
        )

        try:
            # DEPLOY: Configure BGP
            logger.info(f"Deploying BGP to {device}")
            success, message = deploy_bgp_service(nso_client, device, intent, dry_run=False)

            assert success is True, f"Deployment failed: {message}"
            logger.info(f"✓ Deployment successful: {message}")

            # VERIFY: Check BGP is configured
            logger.info(f"Verifying BGP on {device}")
            is_configured = check_bgp_configured(nso_client, device, intent)
            assert is_configured is True, "BGP not found after deployment"
            logger.info("✓ BGP verified")

            # TEST IDEMPOTENCY: Deploy again (should detect no changes)
            logger.info(f"Testing idempotency on {device}")
            success2, message2 = deploy_bgp_service(nso_client, device, intent, dry_run=False)

            assert success2 is True
            assert "already configured" in message2.lower() or "no changes" in message2.lower()
            logger.info(f"✓ Idempotency check passed: {message2}")

        finally:
            # CLEANUP: Remove BGP
            logger.info(f"Removing BGP from {device}")
            success, message = remove_bgp_service(nso_client, device, intent.local_as, dry_run=False)

            if success:
                logger.info(f"✓ Cleanup successful: {message}")
            else:
                logger.warning(f"Cleanup failed: {message}")

    def test_deploy_bgp_with_multiple_neighbors(self, nso_client, sync_device):
        """Test BGP deployment with multiple neighbors."""
        device = sync_device

        intent = BGPPeeringServiceIntent(
            local_as=65096,
            router_id="10.96.96.1",
            neighbors=[
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.96",
                    remote_as=65097,
                    description="Neighbor 1",
                ),
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.95",
                    remote_as=65097,
                    description="Neighbor 2",
                    password="Password123",
                ),
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.94",
                    remote_as=65098,
                    description="Neighbor 3",
                    update_source="Loopback100",
                ),
            ],
        )

        try:
            # Deploy
            logger.info(f"Deploying BGP with 3 neighbors to {device}")
            success, message = deploy_bgp_service(nso_client, device, intent, dry_run=False)
            assert success is True

            # Verify
            is_configured = check_bgp_configured(nso_client, device, intent)
            assert is_configured is True
            logger.info("✓ BGP with multiple neighbors deployed successfully")

        finally:
            # Cleanup
            remove_bgp_service(nso_client, device, intent.local_as, dry_run=False)

    def test_remove_bgp_dry_run(self, nso_client, test_device):
        """Test BGP removal in dry-run mode."""
        # Deploy BGP first
        intent = BGPPeeringServiceIntent(
            local_as=65095,
            router_id="10.95.95.1",
            neighbors=[
                BGPNeighborIntent(neighbor_ip="10.0.0.95", remote_as=65096)
            ],
        )

        try:
            deploy_bgp_service(nso_client, test_device, intent, dry_run=False)

            # Try dry-run removal
            success, message = remove_bgp_service(
                nso_client, test_device, intent.local_as, dry_run=True
            )

            assert "DRY-RUN" in message
            logger.info(f"✓ Dry-run removal: {message}")

            # Verify BGP still exists (dry-run shouldn't remove)
            is_configured = check_bgp_configured(nso_client, test_device, intent)
            assert is_configured is True, "BGP was removed during dry-run"

        finally:
            # Real cleanup
            remove_bgp_service(nso_client, test_device, intent.local_as, dry_run=False)


@pytest.mark.nso
class TestBGPIdempotency:
    """Test idempotency of BGP service operations."""

    def test_idempotency_check_accuracy(self, nso_client, sync_device):
        """Test that idempotency check accurately detects configuration."""
        device = sync_device

        intent = BGPPeeringServiceIntent(
            local_as=65094,
            router_id="10.94.94.1",
            neighbors=[
                BGPNeighborIntent(neighbor_ip="10.0.0.94", remote_as=65095)
            ],
        )

        try:
            # Before deployment: should not be configured
            is_configured_before = check_bgp_configured(nso_client, device, intent)
            assert is_configured_before is False

            # Deploy
            deploy_bgp_service(nso_client, device, intent, dry_run=False)

            # After deployment: should be configured
            is_configured_after = check_bgp_configured(nso_client, device, intent)
            assert is_configured_after is True

            # Different AS: should not match
            different_intent = BGPPeeringServiceIntent(
                local_as=65999,  # Different AS
                router_id="10.94.94.1",
                neighbors=[
                    BGPNeighborIntent(neighbor_ip="10.0.0.94", remote_as=65095)
                ],
            )
            is_different = check_bgp_configured(nso_client, device, different_intent)
            assert is_different is False

        finally:
            remove_bgp_service(nso_client, device, intent.local_as, dry_run=False)

    def test_multiple_deployments_idempotent(self, nso_client, sync_device):
        """Test that multiple deployments are truly idempotent."""
        device = sync_device

        intent = BGPPeeringServiceIntent(
            local_as=65093,
            router_id="10.93.93.1",
            neighbors=[
                BGPNeighborIntent(neighbor_ip="10.0.0.93", remote_as=65094)
            ],
        )

        try:
            # Deploy 3 times
            for i in range(3):
                logger.info(f"Deployment attempt {i+1}/3")
                success, message = deploy_bgp_service(
                    nso_client, device, intent, dry_run=False
                )

                assert success is True

                if i == 0:
                    # First deployment should apply changes
                    assert "deployed" in message.lower() or "applied" in message.lower()
                else:
                    # Subsequent deployments should detect no changes
                    assert (
                        "already configured" in message.lower()
                        or "no changes" in message.lower()
                    )

            logger.info("✓ All 3 deployments were idempotent")

        finally:
            remove_bgp_service(nso_client, device, intent.local_as, dry_run=False)


def test_bgp_intent_validation():
    """Test BGP intent model validation."""
    # Valid intent
    intent = BGPPeeringServiceIntent(
        local_as=65001,
        router_id="10.1.1.1",
        neighbors=[
            BGPNeighborIntent(
                neighbor_ip="10.0.0.2",
                remote_as=65002,
                description="Test",
            )
        ],
    )

    assert intent.local_as == 65001
    assert intent.router_id == "10.1.1.1"
    assert len(intent.neighbors) == 1

    # Invalid AS (too large)
    with pytest.raises(Exception):
        BGPPeeringServiceIntent(
            local_as=4294967296,  # Max is 4294967295
            router_id="10.1.1.1",
            neighbors=[],
        )

    # Invalid router ID format
    with pytest.raises(Exception):
        BGPPeeringServiceIntent(
            local_as=65001,
            router_id="invalid",  # Not an IP
            neighbors=[],
        )

    # Duplicate neighbor IPs
    with pytest.raises(Exception):
        BGPPeeringServiceIntent(
            local_as=65001,
            router_id="10.1.1.1",
            neighbors=[
                BGPNeighborIntent(neighbor_ip="10.0.0.2", remote_as=65002),
                BGPNeighborIntent(neighbor_ip="10.0.0.2", remote_as=65003),  # Duplicate!
            ],
        )


def test_bgp_neighbor_validation():
    """Test BGP neighbor model validation."""
    # Valid neighbor
    neighbor = BGPNeighborIntent(
        neighbor_ip="10.0.0.2",
        remote_as=65002,
        description="Test neighbor",
        password="SecurePass123",
    )

    assert neighbor.neighbor_ip == "10.0.0.2"
    assert neighbor.remote_as == 65002

    # Invalid IP
    with pytest.raises(Exception):
        BGPNeighborIntent(
            neighbor_ip="999.999.999.999",  # Invalid
            remote_as=65002,
        )

    # Invalid AS (too small)
    with pytest.raises(Exception):
        BGPNeighborIntent(
            neighbor_ip="10.0.0.2",
            remote_as=0,  # Min is 1
        )


@pytest.mark.integration
def test_bgp_service_end_to_end_workflow(nso_client, sync_device):
    """Test complete BGP service workflow from intent to deployment."""
    device = sync_device

    # Step 1: Create intent
    intent = BGPPeeringServiceIntent(
        service_name="test-bgp-workflow",
        local_as=65092,
        router_id="10.92.92.1",
        neighbors=[
            BGPNeighborIntent(
                neighbor_ip="10.0.0.92",
                remote_as=65093,
                description="Workflow test neighbor",
            )
        ],
        import_policy="TEST-IMPORT",
        export_policy="TEST-EXPORT",
    )

    try:
        # Step 2: Dry-run
        logger.info("Step 1: Dry-run deployment")
        success, message = deploy_bgp_service(nso_client, device, intent, dry_run=True)
        assert "DRY-RUN" in message

        # Step 3: Deploy
        logger.info("Step 2: Deploy BGP service")
        success, message = deploy_bgp_service(nso_client, device, intent, dry_run=False)
        assert success is True

        # Step 4: Validate
        logger.info("Step 3: Validate deployment")
        is_configured = check_bgp_configured(nso_client, device, intent)
        assert is_configured is True

        # Step 5: Test idempotency
        logger.info("Step 4: Test idempotency")
        success, message = deploy_bgp_service(nso_client, device, intent, dry_run=False)
        assert "already configured" in message.lower()

        # Step 6: Dry-run removal
        logger.info("Step 5: Dry-run removal")
        success, message = remove_bgp_service(
            nso_client, device, intent.local_as, dry_run=True
        )
        assert "DRY-RUN" in message

        logger.info("✓ End-to-end workflow completed successfully")

    finally:
        # Step 7: Remove
        logger.info("Step 6: Remove BGP service")
        remove_bgp_service(nso_client, device, intent.local_as, dry_run=False)