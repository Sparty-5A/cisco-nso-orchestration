"""
Inventory loader for NSO orchestration.

Loads device inventory from YAML files (hosts, groups, defaults) and
provides a unified view of device configurations with variable inheritance.

Unlike Nornir, this is NSO-specific and uses NSO device names directly.
"""

from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class InventoryDevice:
    """Represents a single device with all its properties."""

    def __init__(
        self,
        name: str,
        hostname: str,
        device_type: str,
        ip_address: str | None = None,
        groups: list[str] | None = None,
        vars: dict[str, Any] | None = None,
    ):
        self.name = name
        self.hostname = hostname
        self.device_type = device_type
        self.ip_address = ip_address
        self.groups = groups or []
        self.vars = vars or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable value."""
        return self.vars.get(key, default)

    def __repr__(self) -> str:
        return f"InventoryDevice(name={self.name}, type={self.device_type}, groups={self.groups})"


class Inventory:
    """
    Inventory manager for network devices.

    Loads devices, groups, and defaults from YAML files and provides
    a unified interface for accessing device information with proper
    variable inheritance (defaults → groups → host).
    """

    def __init__(self, inventory_dir: str | Path | None = None):
        """
        Initialize inventory loader.

        Args:
            inventory_dir: Path to inventory directory. If None, uses
                          nso_orchestration/inventory/
        """
        if inventory_dir is None:
            # Default: inventory/ directory relative to this file
            inventory_dir = Path(__file__).parent.parent / "inventory"

        self.inventory_dir = Path(inventory_dir)
        if not self.inventory_dir.exists():
            logger.warning(f"Inventory directory not found: {self.inventory_dir}")
            self.inventory_dir.mkdir(parents=True, exist_ok=True)

        # Load inventory files
        self.defaults = self._load_defaults()
        self.groups = self._load_groups()
        self.devices = self._load_hosts()

        logger.info(
            f"Inventory loaded: {len(self.devices)} devices, "
            f"{len(self.groups)} groups from {self.inventory_dir}"
        )

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file from inventory directory."""
        filepath = self.inventory_dir / filename

        if not filepath.exists():
            logger.warning(f"Inventory file not found: {filepath}")
            return {}

        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
                logger.debug(f"Loaded {filename}: {len(data or {})} entries")
                return data or {}
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return {}

    def _load_defaults(self) -> dict[str, Any]:
        """Load default values."""
        data = self._load_yaml("defaults.yaml")
        return data.get("defaults", {})

    def _load_groups(self) -> dict[str, dict[str, Any]]:
        """Load group definitions."""
        data = self._load_yaml("groups.yaml")
        return data.get("groups", {})

    def _load_hosts(self) -> dict[str, InventoryDevice]:
        """Load host definitions and merge with defaults/groups."""
        data = self._load_yaml("hosts.yaml")
        devices_data = data.get("devices", {})

        devices = {}
        for device_name, device_config in devices_data.items():
            # Start with defaults
            merged_vars = dict(self.defaults)

            # Merge group variables
            device_groups = device_config.get("groups", [])
            for group_name in device_groups:
                if group_name in self.groups:
                    group_vars = self.groups[group_name].get("vars", {})
                    merged_vars.update(group_vars)

            # Merge host-specific variables (highest priority)
            host_vars = device_config.get("vars", {})
            merged_vars.update(host_vars)

            # Create device object
            device = InventoryDevice(
                name=device_name,
                hostname=device_config.get("hostname", device_name),
                device_type=device_config.get("device_type", "unknown"),
                ip_address=device_config.get("ip_address"),
                groups=device_groups,
                vars=merged_vars,
            )

            devices[device_name] = device

        return devices

    def get_device(self, name: str) -> InventoryDevice | None:
        """Get device by name."""
        return self.devices.get(name)

    def get_devices(
        self,
        group: str | None = None,
        device_type: str | None = None,
        **filters,
    ) -> list[InventoryDevice]:
        """
        Get devices matching filters.

        Args:
            group: Filter by group name
            device_type: Filter by device type (ios-xe, ios-xr, etc.)
            **filters: Additional key=value filters on device vars

        Returns:
            List of matching devices

        Examples:
            # Get all distribution routers
            devices = inv.get_devices(group="distribution")

            # Get all IOS-XE devices
            devices = inv.get_devices(device_type="ios-xe")

            # Get devices in west region
            devices = inv.get_devices(region="west")

            # Combined filters
            devices = inv.get_devices(group="distribution", region="west")
        """
        matched = []

        for device in self.devices.values():
            # Filter by group
            if group and group not in device.groups:
                continue

            # Filter by device type
            if device_type and device.device_type != device_type:
                continue

            # Filter by custom vars
            if filters:
                match = True
                for key, value in filters.items():
                    if device.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            matched.append(device)

        logger.debug(
            f"Filtered devices: {len(matched)} matched "
            f"(group={group}, device_type={device_type}, filters={filters})"
        )

        return matched

    def get_device_names(self, **filters) -> list[str]:
        """Get list of device names matching filters."""
        devices = self.get_devices(**filters)
        return [d.name for d in devices]

    def list_groups(self) -> list[str]:
        """Get list of all group names."""
        return list(self.groups.keys())

    def list_devices(self) -> list[str]:
        """Get list of all device names."""
        return list(self.devices.keys())

    def get_group_devices(self, group_name: str) -> list[InventoryDevice]:
        """Get all devices in a specific group."""
        return self.get_devices(group=group_name)

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate inventory for common issues.

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Check for duplicate device names
        device_names = list(self.devices.keys())
        if len(device_names) != len(set(device_names)):
            duplicates = [name for name in device_names if device_names.count(name) > 1]
            issues.append(f"Duplicate device names: {set(duplicates)}")

        # Check for devices with unknown groups
        for device_name, device in self.devices.items():
            for group in device.groups:
                if group not in self.groups:
                    issues.append(
                        f"Device '{device_name}' references unknown group '{group}'"
                    )

        # Check for missing required fields
        for device_name, device in self.devices.items():
            if not device.hostname:
                issues.append(f"Device '{device_name}' missing hostname")
            if not device.device_type:
                issues.append(f"Device '{device_name}' missing device_type")

        is_valid = len(issues) == 0

        if is_valid:
            logger.info("✓ Inventory validation passed")
        else:
            logger.warning(f"✗ Inventory validation failed: {len(issues)} issues")
            for issue in issues:
                logger.warning(f"  - {issue}")

        return is_valid, issues


# Convenience function
def load_inventory(inventory_dir: str | Path | None = None) -> Inventory:
    """Load inventory from directory."""
    return Inventory(inventory_dir=inventory_dir)


# Example usage
if __name__ == "__main__":
    # Load inventory
    inv = load_inventory()

    print(f"\n{'='*60}")
    print(f"Loaded {len(inv.devices)} devices")
    print(f"{'='*60}\n")

    # List all devices
    print("All devices:")
    for name in inv.list_devices():
        device = inv.get_device(name)
        print(f"  - {name} ({device.device_type}) - groups: {device.groups}")

    # Filter examples
    print("\n\nDistribution routers:")
    for device in inv.get_devices(group="distribution"):
        print(f"  - {device.name}: BGP AS {device.get('bgp_as')}")

    print("\n\nIOS-XE devices:")
    for device in inv.get_devices(device_type="ios-xe"):
        print(f"  - {device.name}")

    print("\n\nDevices in west region:")
    for device in inv.get_devices(region="west"):
        print(f"  - {device.name}: {device.get('loopback0_ip')}")

    # Validation
    print("\n\nValidation:")
    is_valid, issues = inv.validate()
    if is_valid:
        print("✓ Inventory is valid")
    else:
        print("✗ Inventory has issues:")
        for issue in issues:
            print(f"  - {issue}")