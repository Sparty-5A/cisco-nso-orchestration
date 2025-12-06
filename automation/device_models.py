"""
Intent models for network configuration using Pydantic.

These models define the desired state of the network and validate
configuration before it's pushed to devices.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoopbackIntent(BaseModel):
    """Intent model for a loopback interface."""

    id: int = Field(..., ge=0, le=2147483647, description="Loopback interface number")
    ipv4: str = Field(
        ..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", description="IPv4 address"
    )
    netmask: str = Field(..., description="Subnet mask")
    description: str | None = Field(None, max_length=240, description="Interface description")

    @field_validator("netmask")
    @classmethod
    def validate_netmask(cls, v: str) -> str:
        """Validate subnet mask format."""
        valid_masks = {
            "255.255.255.255",
            "255.255.255.254",
            "255.255.255.252",
            "255.255.255.248",
            "255.255.255.240",
            "255.255.255.224",
            "255.255.255.192",
            "255.255.255.128",
            "255.255.255.0",
            "255.255.254.0",
            "255.255.252.0",
            "255.255.248.0",
            "255.255.240.0",
            "255.255.224.0",
            "255.255.192.0",
            "255.255.128.0",
            "255.255.0.0",
            "255.254.0.0",
            "255.252.0.0",
            "255.248.0.0",
            "255.240.0.0",
            "255.224.0.0",
            "255.192.0.0",
            "255.128.0.0",
            "255.0.0.0",
            "254.0.0.0",
            "252.0.0.0",
            "248.0.0.0",
            "240.0.0.0",
            "224.0.0.0",
            "192.0.0.0",
            "128.0.0.0",
            "0.0.0.0",
        }
        if v not in valid_masks:
            raise ValueError(f"Invalid subnet mask: {v}. Must be a valid dotted-decimal mask.")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Validate description doesn't contain problematic characters."""
        if v is None:
            return v

        invalid_chars = ["<", ">", "&", '"', "'"]
        if any(char in v for char in invalid_chars):
            raise ValueError(f"Description contains invalid characters: {invalid_chars}")

        return v

    @field_validator("ipv4")
    @classmethod
    def validate_ipv4(cls, v: str) -> str:
        """Validate IPv4 address format and ranges."""
        octets = v.split(".")

        # Check each octet is 0-255
        for octet in octets:
            num = int(octet)
            if not 0 <= num <= 255:
                raise ValueError(f"Invalid IPv4 address: {v}. Octets must be 0-255.")

        # Warn about reserved ranges (but don't reject)
        first_octet = int(octets[0])
        if first_octet == 0:
            raise ValueError("IPv4 address cannot start with 0 (reserved)")
        if first_octet >= 224:
            raise ValueError(f"IPv4 address {v} is in reserved range (224+)")

        return v


class BGPNeighborIntent(BaseModel):
    """Intent model for a BGP neighbor."""

    ip: str = Field(..., description="Neighbor IP address")
    remote_asn: int = Field(..., ge=1, le=4294967295, description="Remote AS number")
    description: str | None = Field(None, max_length=80)
    update_source: str | None = Field(None, description="Update source interface")


class BGPIntent(BaseModel):
    """Intent model for BGP configuration."""

    asn: int = Field(..., ge=1, le=4294967295, description="Local AS number")
    router_id: str | None = Field(None, description="BGP router ID")
    neighbors: list[BGPNeighborIntent] = Field(default_factory=list)


class DeviceIntent(BaseModel):
    """Intent model for a network device."""

    name: str = Field(..., min_length=1, max_length=63, description="Device hostname")
    device_type: Literal["ios", "ios-xe", "ios-xr", "nxos"] = Field(
        ..., description="Device OS type"
    )
    loopbacks: list[LoopbackIntent] = Field(default_factory=list)
    bgp: BGPIntent | None = None

    # Deletion behavior control
    delete_unmanaged_loopbacks: bool = Field(
        default=False,
        description=(
            "If True, delete loopbacks not in intent. "
            "If False (default), only manage declared loopbacks and ignore others. "
            "Safe default prevents accidental deletion of existing configs."
        ),
    )

    delete_unmanaged_bgp_neighbors: bool = Field(
        default=False,
        description=(
            "If True, delete BGP neighbors not in intent. "
            "If False (default), only manage declared neighbors and ignore others. "
            "Safe default prevents accidental deletion of existing BGP sessions."
        ),
    )

    @field_validator("name")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname format."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Invalid hostname: {v}. Only alphanumeric, hyphens, underscores allowed."
            )
        return v


class NetworkIntent(BaseModel):
    """Full network intent - the source of truth."""

    devices: list[DeviceIntent] = Field(..., min_length=1)

    @field_validator("devices")
    @classmethod
    def validate_unique_devices(cls, v: list[DeviceIntent]) -> list[DeviceIntent]:
        """Ensure device names are unique."""
        names = [d.name for d in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Duplicate device names found: {set(duplicates)}")
        return v

    def get_device(self, name: str) -> DeviceIntent | None:
        """Get device intent by name."""
        for device in self.devices:
            if device.name == name:
                return device
        return None


# Example usage and validation
if __name__ == "__main__":
    import json

    # Example intent
    intent_data = {
        "devices": [
            {
                "name": "dist-rtr01",
                "device_type": "ios-xe",
                "delete_unmanaged_loopbacks": False,
                "delete_unmanaged_bgp_neighbors": False,
                "loopbacks": [
                    {
                        "id": 100,
                        "ipv4": "10.100.100.1",
                        "netmask": "255.255.255.255",
                        "description": "Management loopback",
                    },
                    {
                        "id": 200,
                        "ipv4": "10.200.200.1",
                        "netmask": "255.255.255.255",
                        "description": "BGP peering",
                    },
                ],
                "bgp": {
                    "asn": 65001,
                    "router_id": "10.100.100.1",
                    "neighbors": [
                        {"ip": "10.0.0.2", "remote_asn": 65002, "description": "Core router"}
                    ],
                },
            }
        ]
    }

    # Validate
    try:
        intent = NetworkIntent(**intent_data)
        print("✓ Intent validation passed!")
        print(json.dumps(intent.model_dump(), indent=2))
    except Exception as e:
        print(f"✗ Intent validation failed: {e}")