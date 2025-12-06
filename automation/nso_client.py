"""
NSO RESTCONF Client with safe getters and comprehensive error handling.

This module provides a clean interface to Cisco NSO's RESTCONF API with:
- Safe getter pattern with logging
- Transaction management
- Device sync operations
- Rollback capabilities
- Built on httpx for modern HTTP/2 support and type safety
"""

from typing import Any

import httpx
import urllib3
from loguru import logger

# Suppress SSL warnings for sandbox environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NSOClient:
    """Client for interacting with Cisco NSO via RESTCONF API using httpx."""

    def __init__(
        self,
        host: str,
        port: int = 8080,
        username: str = "developer",
        password: str = "C1sco12345",
        verify_ssl: bool = False,
        use_https: bool = False,
        timeout: float = 30.0,
    ):
        """
        Initialize NSO client.

        Args:
            host: NSO server hostname or IP
            port: RESTCONF port (default 8080)
            username: NSO username
            password: NSO password
            verify_ssl: Verify SSL certificates (False for sandbox)
            timeout: Default timeout for requests in seconds
        """
        protocol = "https" if use_https else "http"
        self.host = host
        self.port = port
        self.base_url = f"{protocol}://{host}:{port}/restconf"
        self.auth = (username, password)
        self.verify = verify_ssl
        self.timeout = timeout

        # Create httpx client with default headers
        self.client = httpx.Client(
            verify=self.verify,
            headers={
                "Content-Type": "application/yang-data+json",
                "Accept": "application/yang-data+json",
            },
            timeout=self.timeout,
        )

        logger.info(f"Initialized NSO client for {host}:{port}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close client."""
        self.close()

    def close(self):
        """Close the httpx client."""
        self.client.close()
        logger.debug("NSO client closed")

    def _safe_get(self, url: str, **kwargs) -> dict[str, Any] | None:
        """
        Safe GET request with error handling and logging.

        Args:
            url: Full URL to query
            **kwargs: Additional httpx arguments

        Returns:
            JSON response as dict, or None on error
        """
        try:
            logger.debug(f"GET {url}")
            resp = self.client.get(url, auth=self.auth, **kwargs)
            resp.raise_for_status()

            if resp.status_code == 204:
                logger.debug("Received 204 No Content")
                return {}

            return resp.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error on GET {url}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.TimeoutException:
            logger.error(f"Timeout on GET {url}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request failed on GET {url}: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"Invalid JSON response from {url}: {str(e)}")
            return None

    def _safe_post(
        self, url: str, payload: dict[str, Any] | str, content_type: str | None = None, **kwargs
    ) -> httpx.Response | None:
        """Safe POST request with error handling."""
        try:
            logger.debug(f"POST {url}")

            # Handle XML payloads
            if isinstance(payload, str) and content_type:
                headers = {"Content-Type": content_type, "Accept": "application/yang-data+json"}
                resp = self.client.post(
                    url, content=payload, auth=self.auth, headers=headers, **kwargs
                )
            else:
                # Normal JSON payload
                resp = self.client.post(url, json=payload, auth=self.auth, **kwargs)

            resp.raise_for_status()
            return resp

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error on POST {url}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request failed on POST {url}: {str(e)}")
            return None

    def _safe_patch(self, url: str, payload: dict[str, Any], **kwargs) -> httpx.Response | None:
        """Safe PATCH request with error handling."""
        try:
            logger.debug(f"PATCH {url}")
            resp = self.client.patch(url, json=payload, auth=self.auth, **kwargs)
            resp.raise_for_status()
            return resp

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error on PATCH {url}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request failed on PATCH {url}: {str(e)}")
            return None

    def _safe_delete(self, url: str, **kwargs) -> httpx.Response | None:
        """Safe DELETE request with error handling."""
        try:
            logger.debug(f"DELETE {url}")
            resp = self.client.delete(url, auth=self.auth, **kwargs)
            resp.raise_for_status()
            return resp

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error on DELETE {url}: {e.response.status_code} - {e.response.text}"
            )
            return None
        except httpx.RequestError as e:
            logger.error(f"Request failed on DELETE {url}: {str(e)}")
            return None

    def health_check(self) -> bool:
        """
        Verify NSO is reachable and responsive.

        Returns:
            True if NSO responds successfully
        """
        url = f"{self.base_url}/data/tailf-ncs:devices"
        result = self._safe_get(url)

        if result is not None:
            logger.info("✓ NSO health check passed")
            return True
        else:
            logger.error("✗ NSO health check failed")
            return False

    def get_devices(self) -> list[str] | None:
        """
        Get list of all managed devices.

        Returns:
            List of device names, or None on error
        """
        url = f"{self.base_url}/data/tailf-ncs:devices/device"
        result = self._safe_get(url)

        if result and "tailf-ncs:device" in result:
            devices = [d["name"] for d in result["tailf-ncs:device"]]
            logger.info(f"Found {len(devices)} devices: {devices}")
            return devices

        logger.warning("No devices found or query failed")
        return None

    def sync_from_device(self, device_name: str) -> bool:
        """
        Sync configuration from device to NSO (sync-from).

        Args:
            device_name: Name of device to sync

        Returns:
            True if sync successful
        """
        url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/sync-from"
        payload = {"input": {}}

        logger.info(f"Syncing from device: {device_name}")
        resp = self._safe_post(url, payload)

        if resp and resp.status_code in (200, 204):
            logger.info(f"✓ Sync-from successful for {device_name}")
            return True

        logger.error(f"✗ Sync-from failed for {device_name}")
        return False

    def get_device_config(self, device_name: str) -> dict[str, Any] | None:
        """
        Get full configuration for a device from NSO CDB.

        Args:
            device_name: Name of device

        Returns:
            Device config as dict, or None on error
        """
        url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config"
        result = self._safe_get(url)

        if result:
            logger.info(f"Retrieved config for {device_name}")
            return result

        logger.error(f"Failed to get config for {device_name}")
        return None

    def get_interface_config(
        self, device_name: str, interface_type: str, interface_id: str
    ) -> dict[str, Any] | None:
        """Get specific interface configuration."""
        # Change from Loopback=100 to Loopback/100
        url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config/tailf-ned-cisco-ios:interface/{interface_type}={interface_id}"
        result = self._safe_get(url)

        if result:
            logger.info(f"Retrieved {interface_type}{interface_id} config from {device_name}")
            return result

        logger.warning(f"{interface_type}{interface_id} not found on {device_name}")
        return None

    def configure_loopback(
        self,
        device_name: str,
        loopback_id: str,
        ip_address: str,
        netmask: str,
        description: str | None = None,
        dry_run: bool = False,  # NEW parameter
    ) -> bool | dict[str, Any]:  # Can return True or dry-run results
        """
        Configure a loopback interface on IOS XE device.

        Args:
            device_name: Target device
            loopback_id: Loopback number
            ip_address: IP address
            netmask: Subnet mask
            description: Optional description
            dry_run: If True, return diff without applying changes

        Returns:
            True if successful, or dict with dry-run results if dry_run=True
        """
        # Build URL with optional dry-run parameter
        base_url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config/tailf-ned-cisco-ios:interface"
        url = f"{base_url}?dry-run=native" if dry_run else base_url

        desc_xml = f"<description>{description}</description>" if description else ""
        xml_payload = f"""
        <Loopback>
            <name>{loopback_id}</name>
            {desc_xml}
                <ip>
                    <address>
                        <primary>
                            <address>{ip_address}</address>
                            <mask>{netmask}</mask>
                        </primary>
                    </address>
                </ip>
        </Loopback>"""

        logger.info(
            f"{'[DRY-RUN] ' if dry_run else ''}Configuring Loopback{loopback_id} on {device_name}: {ip_address}/{netmask}"
        )
        resp = self._safe_post(url, xml_payload, content_type="application/yang-data+xml")

        if not resp:
            logger.error(f"✗ Failed to configure Loopback{loopback_id}")
            return False

        if resp.status_code in (200, 201, 204):
            if dry_run:
                # Return the diff results
                try:
                    result = resp.json()
                    logger.info(f"✓ Dry-run completed for Loopback{loopback_id}")
                    return result
                except (ValueError, KeyError):
                    logger.info("✓ Dry-run completed (no diff returned)")
                    return {"status": "no-changes"}
            else:
                logger.info(f"✓ Loopback{loopback_id} configured successfully")
                return True

        logger.error(f"✗ Failed to configure Loopback{loopback_id}")
        return False

    def configure_loopback_with_rollback_id(
        self,
        device_name: str,
        loopback_id: str,
        ip_address: str,
        netmask: str,
        description: str | None = None,
    ) -> tuple[bool, int | None]:
        """
        Configure loopback and return its rollback fixed-number.

        Returns:
            Tuple of (success: bool, rollback_fixed_number: int | None)
        """
        url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config/tailf-ned-cisco-ios:interface?rollback-id=true"

        desc_xml = f"<description>{description}</description>" if description else ""
        xml_payload = f"""<Loopback>
      <name>{loopback_id}</name>
      {desc_xml}
      <ip>
        <address>
          <primary>
            <address>{ip_address}</address>
            <mask>{netmask}</mask>
          </primary>
        </address>
      </ip>
    </Loopback>"""

        logger.info(f"Configuring Loopback{loopback_id} with rollback tracking")
        resp = self._safe_post(url, xml_payload, content_type="application/yang-data+xml")

        if not resp or resp.status_code not in (200, 201, 204):
            logger.error(f"✗ Failed to configure Loopback{loopback_id}")
            return False, None

        # Extract rollback-id from response body
        try:
            result = resp.json()
            rollback_fixed_number = (
                result.get("tailf-restconf:result", {}).get("rollback", {}).get("id")
            )

            if rollback_fixed_number:
                logger.info(
                    f"✓ Loopback{loopback_id} configured (rollback fixed-number: {rollback_fixed_number})"
                )
                return True, int(rollback_fixed_number)
            else:
                logger.warning(f"✓ Loopback{loopback_id} configured but no rollback-id in response")
                return True, None

        except (ValueError, KeyError) as e:
            logger.warning(
                f"✓ Loopback{loopback_id} configured but couldn't parse rollback-id: {e}"
            )
            return True, None

    def get_rollback_files(self) -> list[dict[str, Any]] | None:
        """
        Get list of available rollback files.

        Returns:
            List of rollback file info, or None on error
        """
        url = f"{self.base_url}/data/tailf-rollback:rollback-files"
        result = self._safe_get(url)

        if result and "tailf-rollback:rollback-files" in result:
            files = result["tailf-rollback:rollback-files"].get("file", [])
            logger.info(f"Found {len(files)} rollback files")
            return files

        logger.warning("No rollback files found")
        return None

    def rollback(self, rollback_id: int = 0, use_fixed_number: bool = False) -> bool:
        """
        Rollback to a previous configuration.

        Args:
            rollback_id: Rollback identifier
                - If use_fixed_number=False: 0 = most recent, 1 = second most recent, etc.
                - If use_fixed_number=True: Use the fixed-number from the rollback file
            use_fixed_number: Use fixed-number instead of relative id

        Returns:
            True if rollback successful

        Example:
            # Rollback to most recent change
            client.rollback(0)

            # Rollback to specific fixed-number (from POST response)
            client.rollback(10042, use_fixed_number=True)
        """
        url = f"{self.base_url}/data/tailf-rollback:rollback-files/apply-rollback-file"

        # Build XML payload based on id type
        id_element = "fixed-number" if use_fixed_number else "id"
        xml_payload = f"""<input xmlns="http://tail-f.com/ns/rollback">
      <{id_element}>{rollback_id}</{id_element}>
    </input>"""

        logger.warning(f"Rolling back using {id_element}={rollback_id}")
        resp = self._safe_post(url, xml_payload, content_type="application/yang-data+xml")

        if resp and resp.status_code in (200, 201, 204):
            logger.info(f"✓ Rollback to {id_element}={rollback_id} successful")
            return True

        logger.error(f"✗ Rollback to {id_element}={rollback_id} failed")
        return False

    def delete_loopback(self, device_name: str, loopback_id: str) -> bool:
        """Delete a loopback interface."""
        # Change from Loopback=100 to Loopback/100
        url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config/tailf-ned-cisco-ios:interface/Loopback={loopback_id}"

        logger.info(f"Deleting Loopback{loopback_id} from {device_name}")
        resp = self._safe_delete(url)

        if resp and resp.status_code in (200, 204):
            logger.info(f"✓ Loopback{loopback_id} deleted successfully")
            return True

        logger.error(f"✗ Failed to delete Loopback{loopback_id}")
        return False
