"""Tests for intent models and validation."""

import pytest
from pydantic import ValidationError

from automation.device_models import (
    DeviceIntent,
    LoopbackIntent,
    NetworkIntent,
)


def test_valid_loopback():
    """Test valid loopback configuration."""
    lb = LoopbackIntent(
        id=100, ipv4="10.100.100.1", netmask="255.255.255.255", description="Test loopback"
    )
    assert lb.id == 100
    assert lb.ipv4 == "10.100.100.1"


def test_invalid_loopback_netmask():
    """Test invalid netmask is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        LoopbackIntent(
            id=100,
            ipv4="10.100.100.1",
            netmask="255.255.255.256",  # Invalid
        )
    assert "Invalid subnet mask" in str(exc_info.value)


def test_invalid_ipv4_address():
    """Test invalid IPv4 address is rejected."""
    with pytest.raises(ValidationError):
        LoopbackIntent(id=100, ipv4="300.100.100.1", netmask="255.255.255.255")  # Invalid octet


def test_duplicate_device_names():
    """Test duplicate device names are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        NetworkIntent(
            devices=[
                DeviceIntent(name="router1", device_type="ios-xe", loopbacks=[]),
                DeviceIntent(name="router1", device_type="ios-xe", loopbacks=[]),  # Duplicate
            ]
        )
    assert "Duplicate device names" in str(exc_info.value)


def test_valid_network_intent():
    """Test valid complete network intent."""
    intent = NetworkIntent(
        devices=[
            DeviceIntent(
                name="dist-rtr01",
                device_type="ios-xe",
                loopbacks=[LoopbackIntent(id=100, ipv4="10.100.100.1", netmask="255.255.255.255")],
            )
        ]
    )

    assert len(intent.devices) == 1
    assert intent.devices[0].name == "dist-rtr01"
    assert len(intent.devices[0].loopbacks) == 1


def test_safe_deletion_default():
    """Test delete_unmanaged_loopbacks defaults to False (safe)."""
    device = DeviceIntent(
        name="test-rtr",
        device_type="ios-xe",
        loopbacks=[LoopbackIntent(id=100, ipv4="10.100.100.1", netmask="255.255.255.255")],
    )

    # Default should be False (safe mode)
    assert device.delete_unmanaged_loopbacks is False


def test_strict_deletion_explicit():
    """Test delete_unmanaged_loopbacks can be set to True."""
    device = DeviceIntent(
        name="test-rtr",
        device_type="ios-xe",
        delete_unmanaged_loopbacks=True,  # Explicitly enable
        loopbacks=[],
    )

    assert device.delete_unmanaged_loopbacks is True


def test_mixed_deletion_policies():
    """Test different devices can have different deletion policies."""
    intent = NetworkIntent(
        devices=[
            DeviceIntent(
                name="safe-rtr",
                device_type="ios-xe",
                delete_unmanaged_loopbacks=False,
                loopbacks=[],
            ),
            DeviceIntent(
                name="strict-rtr",
                device_type="ios-xe",
                delete_unmanaged_loopbacks=True,
                loopbacks=[],
            ),
        ]
    )

    assert intent.devices[0].delete_unmanaged_loopbacks is False
    assert intent.devices[1].delete_unmanaged_loopbacks is True
