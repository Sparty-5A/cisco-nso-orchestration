"""
Service-based intent models for network services.

These models represent complete network services (BGP peering, OSPF, etc.)
rather than individual resources. A service groups related configuration
elements that should be deployed together.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal


class BGPNeighborIntent(BaseModel):
    """Intent for a single BGP neighbor configuration."""

    neighbor_ip: str = Field(..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    remote_as: int = Field(..., ge=1, le=4294967295, description="Remote AS number")
    description: str | None = Field(None, max_length=240)
    password: str | None = Field(None, min_length=1, max_length=80, description="MD5 auth password")
    update_source: str | None = Field(None, description="Update source interface (e.g., Loopback0)")

    @field_validator("neighbor_ip")
    @classmethod
    def validate_neighbor_ip(cls, v: str) -> str:
        """Validate neighbor IP address."""
        octets = v.split(".")
        for octet in octets:
            num = int(octet)
            if not 0 <= num <= 255:
                raise ValueError(f"Invalid IP address: {v}")
        return v


class BGPPeeringServiceIntent(BaseModel):
    """
    Intent for BGP peering service.

    This service includes:
    - BGP process configuration
    - Router ID
    - One or more BGP neighbors
    - Import/export policies (references)
    """

    service_name: str = Field(default="bgp-peering", description="Service identifier")
    local_as: int = Field(..., ge=1, le=4294967295, description="Local AS number")
    router_id: str = Field(..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", description="BGP router ID")
    neighbors: list[BGPNeighborIntent] = Field(..., min_length=1, description="BGP neighbors to configure")

    # Policy references (assumed to exist on device)
    import_policy: str | None = Field(None, description="Import policy name")
    export_policy: str | None = Field(None, description="Export policy name")

    @field_validator("router_id")
    @classmethod
    def validate_router_id(cls, v: str) -> str:
        """Validate router ID format."""
        octets = v.split(".")
        if len(octets) != 4:
            raise ValueError(f"Invalid router ID: {v}")
        for octet in octets:
            num = int(octet)
            if not 0 <= num <= 255:
                raise ValueError(f"Invalid router ID: {v}")
        return v

    @field_validator("neighbors")
    @classmethod
    def validate_unique_neighbors(cls, v: list[BGPNeighborIntent]) -> list[BGPNeighborIntent]:
        """Ensure neighbor IPs are unique."""
        neighbor_ips = [n.neighbor_ip for n in v]
        if len(neighbor_ips) != len(set(neighbor_ips)):
            duplicates = [ip for ip in neighbor_ips if neighbor_ips.count(ip) > 1]
            raise ValueError(f"Duplicate neighbor IPs: {set(duplicates)}")
        return v


class ServiceDeploymentIntent(BaseModel):
    """
    Intent for deploying a service to target devices.

    This is the top-level intent that specifies:
    - Which service to deploy
    - Which devices to target
    - Service-specific configuration
    """

    service_type: Literal["bgp-peering", "ospf", "loopback"] = Field(..., description="Type of service")
    target_devices: list[str] = Field(..., min_length=1, description="Device names to deploy to")

    # Service-specific config (one of these will be populated)
    bgp_config: BGPPeeringServiceIntent | None = None

    @field_validator("target_devices")
    @classmethod
    def validate_unique_devices(cls, v: list[str]) -> list[str]:
        """Ensure device names are unique."""
        if len(v) != len(set(v)):
            duplicates = [d for d in v if v.count(d) > 1]
            raise ValueError(f"Duplicate device names: {set(duplicates)}")
        return v

    def model_post_init(self, __context):
        """Validate that service config matches service type."""
        if self.service_type == "bgp-peering" and self.bgp_config is None:
            raise ValueError("bgp_config required when service_type is 'bgp-peering'")


# Example usage for reference
if __name__ == "__main__":
    # Example: BGP peering service
    service_intent = ServiceDeploymentIntent(
        service_type="bgp-peering",
        target_devices=["dist-rtr01", "dist-rtr02"],
        bgp_config=BGPPeeringServiceIntent(
            local_as=65001,
            router_id="10.100.100.1",
            neighbors=[
                BGPNeighborIntent(
                    neighbor_ip="10.0.0.2",
                    remote_as=65002,
                    description="To core-rtr01",
                    password="SecurePassword123"
                )
            ],
            import_policy="BGP-IMPORT-POLICY",
            export_policy="BGP-EXPORT-POLICY"
        )
    )

    print("✓ Service intent validation passed!")
    print(service_intent.model_dump_json(indent=2))