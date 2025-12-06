"""
Pytest fixtures for NSO testing.

Provides reusable test fixtures for NSO client initialization,
device management, inventory loading, service orchestration,
and test cleanup.
"""

import pytest
from decouple import config
from loguru import logger

from nso_orchestration.automation.inventory_loader import load_inventory
from nso_orchestration.automation.nso_client import NSOClient
from nso_orchestration.automation.service_orchestrator import ServiceOrchestrator
from nso_orchestration.automation.template_renderer import TemplateRenderer

# Configure loguru for tests
logger.remove()  # Remove default handler
logger.add("logs/test_{time}.log", rotation="1 day", retention="7 days", level="DEBUG")
logger.add(lambda msg: print(msg, end=""), level="INFO", colorize=True)  # Console output


# ===== NSO Client Fixtures =====

@pytest.fixture(scope="session")
def nso_credentials():
    """NSO credentials from environment variables."""
    return {
        "host": config("NSO_HOST", default="10.10.20.49"),
        "port": config("NSO_PORT", default=8080, cast=int),
        "username": config("NSO_USER", default="developer"),
        "password": config("NSO_PW", default="C1sco12345"),
    }


@pytest.fixture(scope="session")
def nso_client_session(nso_credentials):
    """
    Session-scoped NSO client for health checks and device discovery.

    Use this for read-only operations that can be shared across tests.
    """
    logger.info("Creating session-scoped NSO client")
    client = NSOClient(**nso_credentials)

    # Verify connectivity
    if not client.health_check():
        pytest.skip("NSO is not reachable - skipping tests")

    yield client

    logger.info("Tearing down session-scoped NSO client")


@pytest.fixture(scope="function")
def nso_client(nso_credentials):
    """
    Function-scoped NSO client for tests that modify configuration.

    Each test gets a fresh client instance. Use this for write operations
    to ensure proper isolation.
    """
    logger.info("Creating function-scoped NSO client")
    client = NSOClient(**nso_credentials)

    yield client

    logger.info("Tearing down function-scoped NSO client")


# ===== Device Fixtures =====

@pytest.fixture(scope="session")
def available_devices(nso_client_session):
    """
    Discover available devices in NSO.

    Returns a list of device names that can be used in tests.
    If no devices found, skip all tests.
    """
    logger.info("Discovering devices from NSO")
    devices = nso_client_session.get_devices()

    if not devices:
        pytest.skip("No devices found in NSO - cannot run tests")

    logger.info(f"Available devices: {devices}")
    return devices


@pytest.fixture(scope="function")
def test_device(available_devices):
    """
    Provide a single test device for simple tests.

    Returns an IOS-XE device (not IOS XR), or skips if none available.
    """
    # Prefer IOS-XE devices (dist-rtr, internet-rtr, dev-dist-rtr)
    for device in available_devices:
        if any(keyword in device.lower() for keyword in ["dist-rtr", "internet-rtr", "dev-dist"]):
            logger.info(f"Selected IOS-XE test device: {device}")
            return device

    # Fallback: any device with 'rtr' but NOT 'core' (which is IOS XR)
    for device in available_devices:
        if "rtr" in device.lower() and "core" not in device.lower():
            logger.info(f"Selected test device: {device}")
            return device

    pytest.skip("No suitable IOS-XE device found for testing")


@pytest.fixture(scope="function")
def sync_device(nso_client, test_device):
    """
    Ensure test device is synced before test runs.

    Performs sync-from at start of each test to ensure NSO has
    latest device state.
    """
    logger.info(f"Pre-test sync for {test_device}")
    success = nso_client.sync_from_device(test_device)

    if not success:
        pytest.skip(f"Could not sync {test_device} - device may be unreachable")

    return test_device


# ===== Inventory Fixtures =====

@pytest.fixture(scope="session")
def inventory():
    """
    Session-scoped inventory fixture.

    Loads inventory once and shares across all tests.
    """
    logger.info("Loading inventory for tests")
    inv = load_inventory()

    # Validate inventory
    is_valid, issues = inv.validate()
    if not is_valid:
        logger.warning("Inventory validation issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")

    logger.info(f"Inventory loaded: {len(inv.devices)} devices, {len(inv.groups)} groups")
    return inv


@pytest.fixture(scope="function")
def inventory_device(inventory, test_device):
    """
    Get inventory data for the test device.

    Returns InventoryDevice object with all variables merged.
    """
    device = inventory.get_device(test_device)
    if device:
        logger.info(f"Inventory data for {test_device}: groups={device.groups}")
        return device
    else:
        logger.warning(f"Device {test_device} not found in inventory")
        return None


# ===== Service Orchestration Fixtures =====

@pytest.fixture(scope="function")
def service_orchestrator(nso_client, inventory):
    """
    Service orchestrator fixture with NSO client and inventory.

    Use this for testing service deployments.
    """
    logger.info("Creating service orchestrator")
    orch = ServiceOrchestrator(
        nso_client=nso_client,
        inventory=inventory,
        max_workers=2  # Lower for testing to avoid overwhelming NSO
    )
    return orch


# ===== Template Renderer Fixtures =====

@pytest.fixture(scope="session")
def template_renderer():
    """
    Session-scoped template renderer.

    Use for testing template rendering without NSO.
    """
    logger.info("Creating template renderer")
    renderer = TemplateRenderer()
    return renderer


# ===== Test Data Fixtures =====

@pytest.fixture(scope="function")
def test_loopback_config():
    """
    Sample loopback configuration for testing.

    Returns a dict with test loopback parameters.
    """
    return {
        "loopback_id": "100",
        "ip_address": "10.100.100.1",
        "netmask": "255.255.255.255",
        "description": "TEST_LOOPBACK_DO_NOT_USE",
    }


@pytest.fixture(scope="function")
def test_bgp_config():
    """
    Sample BGP configuration for testing.

    Returns a dict with test BGP parameters using unlikely AS numbers.
    """
    return {
        "local_as": 65099,  # Unlikely to conflict
        "router_id": "10.99.99.1",
        "neighbor_ip": "10.0.0.99",
        "remote_as": 65100,
    }


# ===== Cleanup Fixtures =====

@pytest.fixture(scope="function")
def clean_loopback(nso_client, test_device, request):
    """
    Cleanup fixture for loopback tests.

    Usage in test:
        @pytest.mark.usefixtures("clean_loopback")
        def test_something(nso_client, test_device):
            loopback_id = "100"
            # Test creates Loopback100

    The fixture will automatically clean up Loopback100 after the test.
    """
    # Store loopback IDs created during test
    created_loopbacks = []

    def _register_loopback(loopback_id: str):
        """Register a loopback for cleanup"""
        created_loopbacks.append(loopback_id)

    # Make registration function available to tests
    request.instance.register_loopback = (
        _register_loopback if hasattr(request, "instance") else None
    )

    yield created_loopbacks

    # Cleanup after test
    logger.info(f"Cleaning up loopbacks: {created_loopbacks}")
    for loopback_id in created_loopbacks:
        try:
            nso_client.delete_loopback(test_device, loopback_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup Loopback{loopback_id}: {e}")


@pytest.fixture(scope="function")
def clean_bgp_service(nso_client, test_device):
    """
    Cleanup fixture for BGP service tests.

    Tracks BGP AS numbers deployed during test and removes them afterward.

    Usage:
        def test_bgp(nso_client, test_device, clean_bgp_service):
            as_number = 65099
            clean_bgp_service.register(as_number)
            # Deploy BGP...
            # Automatic cleanup happens after test
    """
    from nso_orchestration.services.bgp_peering import remove_bgp_service

    deployed_as_numbers = []

    class BGPCleaner:
        """Helper to track and clean BGP services."""

        @staticmethod
        def register(as_number: int):
            """Register a BGP AS for cleanup."""
            deployed_as_numbers.append(as_number)
            logger.info(f"Registered BGP AS {as_number} for cleanup")

    yield BGPCleaner()

    # Cleanup after test
    logger.info(f"Cleaning up BGP services: AS {deployed_as_numbers}")
    for as_number in deployed_as_numbers:
        try:
            success, message = remove_bgp_service(
                nso_client, test_device, as_number, dry_run=False
            )
            if success:
                logger.info(f"✓ Cleaned up BGP AS {as_number}")
            else:
                logger.warning(f"Failed to cleanup BGP AS {as_number}: {message}")
        except Exception as e:
            logger.warning(f"Exception cleaning up BGP AS {as_number}: {e}")


# ===== Auto-logging Fixture =====

@pytest.fixture(autouse=True)
def log_test_info(request):
    """
    Automatically log test start/end for all tests.

    This fixture runs for every test automatically.
    """
    test_name = request.node.name
    logger.info(f"{'='*60}")
    logger.info(f"Starting test: {test_name}")
    logger.info(f"{'='*60}")

    yield

    logger.info(f"{'='*60}")
    logger.info(f"Finished test: {test_name}")
    logger.info(f"{'='*60}\n")


# ===== Pytest Configuration =====

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "nso: mark test as requiring NSO connectivity")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "inventory: mark test as requiring inventory")
    config.addinivalue_line("markers", "service: mark test as service deployment test")


def pytest_collection_modifyitems(config, items):
    """
    Automatically mark tests based on their location/name.

    - Tests in test_nso_*.py are marked with @pytest.mark.nso
    - Tests in test_*_service.py are marked with @pytest.mark.service
    - Tests with 'integration' in name are marked @pytest.mark.integration
    """
    for item in items:
        # Mark NSO tests
        if "test_nso" in item.nodeid or "nso_client" in str(item.fixturenames):
            item.add_marker(pytest.mark.nso)

        # Mark service tests
        if "service" in item.nodeid.lower():
            item.add_marker(pytest.mark.service)

        # Mark integration tests
        if "integration" in item.name.lower() or "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)

        # Mark inventory tests
        if "inventory" in str(item.fixturenames):
            item.add_marker(pytest.mark.inventory)
