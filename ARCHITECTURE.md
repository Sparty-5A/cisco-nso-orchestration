# Architecture Documentation

**Complete technical breakdown of the NSO Network Orchestration Framework**

This document provides an exhaustive explanation of every file, function, and design decision in the project.

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Directory Structure](#directory-structure)
- [Intent Files](#intent-files)
- [Inventory System](#inventory-system)
- [Automation Layer](#automation-layer)
- [Services Layer](#services-layer)
- [Templates](#templates)
- [Scripts](#scripts)
- [Tests](#tests)
- [Design Patterns](#design-patterns)
- [Data Flow](#data-flow)

---

## High-Level Architecture

### Layered Design

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: INTENT (Source of Truth)                              │
│  - YAML files declaring desired state                           │
│  - Validated by Pydantic models                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 2: ORCHESTRATION (When & Where)                          │
│  - Loads and merges intent files                                │
│  - Calculates state differences                                 │
│  - Coordinates deployment sequence                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 3: SERVICES (How)                                        │
│  - Reusable deployment functions                                │
│  - Template rendering                                           │
│  - Idempotency checks                                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 4: TRANSPORT (Communication)                             │
│  - NSO RESTCONF API client                                      │
│  - HTTP/HTTPS with authentication                               │
│  - Error handling and retries                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
                    NSO → Devices
```

### Design Philosophy

1. **Separation of Concerns** - Each layer has a specific responsibility
2. **Reusability** - Services layer can be used by multiple orchestrators
3. **Testability** - Each component can be tested independently
4. **Idempotency** - Safe to run repeatedly
5. **Declarative** - Declare desired state, not imperative steps

---

## Directory Structure

```
nso_orchestration/
├── intent/                  # YAML source of truth files
├── inventory/               # Device inventory & variables
├── automation/              # Core orchestration engine
├── services/                # Reusable deployment functions
├── templates/               # Jinja2 config templates
├── scripts/                 # CLI tools
├── tests/                   # Test suite
└── docs/                    # Documentation
```

---

## Intent Files

**Purpose**: Declare desired network state in YAML format

**Location**: `intent/`

### `device_loopbacks.yaml`

**Purpose**: Device-level loopback interface configurations

**Structure**:
```yaml
devices:
  - name: <device-name>
    device_type: ios-xe | ios-xr | nxos | ios
    delete_unmanaged_loopbacks: true | false
    loopbacks:
      - id: <0-2147483647>
        ipv4: <ip-address>
        netmask: <subnet-mask>
        description: <optional-text>
```

**Key Features**:
- Each device can have multiple loopbacks
- Deletion policy per device (safe vs strict)
- Validated by `LoopbackIntent` Pydantic model

**Example**:
```yaml
devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_loopbacks: false  # Safe mode
    loopbacks:
      - id: 100
        ipv4: 10.100.100.1
        netmask: 255.255.255.255
        description: "Management loopback"
```

**Validation Rules**:
- `id`: 0-2147483647 (32-bit integer)
- `ipv4`: Valid IPv4 address (regex validated)
- `netmask`: Must be valid dotted-decimal mask
- `description`: Max 240 characters, no special chars

---

### `device_bgp_configs.yaml`

**Purpose**: Device-level BGP routing configurations

**Structure**:
```yaml
devices:
  - name: <device-name>
    device_type: ios-xe | ios-xr
    delete_unmanaged_bgp_neighbors: true | false
    bgp:
      asn: <1-4294967295>
      router_id: <ip-address>
      neighbors:
        - ip: <neighbor-ip>
          remote_asn: <1-4294967295>
          description: <optional>
          update_source: <interface-name>
```

**Key Features**:
- Device-specific router-IDs (critical for BGP!)
- Per-device neighbor relationships
- Deletion policy for BGP neighbors
- Validated by `BGPIntent` Pydantic model

**Example**:
```yaml
devices:
  - name: core-rtr01
    device_type: ios-xr
    delete_unmanaged_bgp_neighbors: false
    bgp:
      asn: 65001
      router_id: 10.200.200.1          # Unique!
      neighbors:
        - ip: 10.100.100.1             # Points to dist-rtr01
          remote_asn: 65001
          description: "iBGP to dist-rtr01"
          update_source: "Loopback0"
```

**Why Device-Level (not Service-Level)**:
- Each router needs unique router-ID
- Each router has different neighbor relationships
- Not a "service" where config is identical across devices

**Validation Rules**:
- `asn`: 1-4294967295 (32-bit AS number)
- `router_id`: Valid IPv4 address
- `neighbors`: Array of unique neighbor IPs
- Duplicate neighbor IPs rejected

---

### `_deprecated/`

**Purpose**: Archived intent files (service-level BGP - wrong pattern)

**Files**:
- `service_bgp_development.yaml`
- `service_bgp_peering.yaml`
- `service_bgp_production.yaml`
- `README.md` (explains why deprecated)

**Why Deprecated**:
These files treated BGP as a "service" with same config for all devices, which doesn't work because:
- Can't use same router-ID for multiple devices
- Each device has different neighbors
- Not a true "service" pattern

**Kept for Reference**: Shows what NOT to do, and provides examples for future true services (L3VPN, VRF, etc.)

---

## Inventory System

**Purpose**: Device metadata with variable inheritance

**Location**: `inventory/`

**Pattern**: Defaults → Groups → Host (highest priority wins)

### `defaults.yaml`

**Purpose**: Default values applied to ALL devices

**Structure**:
```yaml
defaults:
  nso_host: 10.10.20.49
  nso_port: 8080
  dns_servers: [8.8.8.8, 8.8.4.4]
  ntp_servers: [10.1.1.10, 10.1.1.11]
  # ... many more defaults
```

**Use Case**: Organization-wide settings that rarely change

**Examples**:
- NSO connection details
- DNS/NTP servers
- Logging configuration
- SNMP community strings

---

### `groups.yaml`

**Purpose**: Group definitions with shared variables

**Structure**:
```yaml
groups:
  distribution:
    description: "Distribution layer routers"
    vars:
      layer: distribution
      bgp_as: 65001
  
  production:
    description: "Production environment"
    vars:
      environment: prod
      backup_enabled: true
```

**Use Case**: Categorize devices by role, location, or environment

**Inheritance**: Group vars override defaults

**Examples**:
- `core`: Core routers (AS 65000)
- `distribution`: Distribution routers (AS 65001)
- `production`: Prod devices (backup enabled)
- `development`: Dev devices (backup disabled)

---

### `hosts.yaml`

**Purpose**: Individual device definitions

**Structure**:
```yaml
devices:
  dist-rtr01:
    hostname: dist-rtr01
    ip_address: 10.10.20.175
    device_type: ios-xe
    protocol: ssh
    groups:
      - distribution
      - router
      - production
      - bgp_enabled
    vars:
      loopback0_ip: 10.100.100.1
      bgp_router_id: 10.100.100.1
      bgp_as: 65001
```

**Use Case**: Device-specific overrides

**Inheritance**: Host vars override group vars override defaults

**Critical Fields**:
- `device_type`: Used to select correct template (ios-xe vs ios-xr)
- `groups`: Determines which group vars to inherit
- `vars`: Device-specific values (highest priority)

**Variable Resolution Example**:
```python
# Final value for dist-rtr01:
nso_host = "10.10.20.49"          # From defaults.yaml
bgp_as = 65001                     # From distribution group
loopback0_ip = "10.100.100.1"     # From host vars (overrides all)
```

---

### `inventory_loader.py`

**Purpose**: Load and merge inventory with variable inheritance

**Location**: `automation/inventory_loader.py`

**Key Classes**:

#### `InventoryDevice`
Represents a single device with all merged variables.

```python
class InventoryDevice:
    def __init__(self, name, hostname, device_type, ip_address, groups, vars):
        self.name = name
        self.hostname = hostname
        self.device_type = device_type  # Critical for template selection!
        self.ip_address = ip_address
        self.groups = groups
        self.vars = vars  # Merged: defaults → groups → host
    
    def get(self, key, default=None):
        """Get variable value with fallback"""
```

#### `Inventory`
Manages device collection and filtering.

**Key Methods**:
```python
def get_device(name: str) -> InventoryDevice:
    """Get device by name"""

def get_devices(group=None, device_type=None, **filters) -> list[InventoryDevice]:
    """Get devices matching filters"""
    # Examples:
    # get_devices(group="distribution")
    # get_devices(device_type="ios-xe")
    # get_devices(region="west", environment="prod")

def validate() -> tuple[bool, list[str]]:
    """Validate inventory for issues"""
    # Checks: duplicate names, unknown groups, missing fields
```

**Usage Pattern**:
```python
from nso_orchestration.automation.inventory_loader import load_inventory

inv = load_inventory()
device = inv.get_device("dist-rtr01")
print(device.device_type)  # "ios-xe"
print(device.get("bgp_as"))  # 65001 (from group)
```

**Variable Inheritance Implementation**:
```python
# Start with defaults
merged_vars = dict(self.defaults)

# Apply group variables
for group_name in device_groups:
    group_vars = self.groups[group_name].get("vars", {})
    merged_vars.update(group_vars)  # Overwrites defaults

# Apply host variables (highest priority)
host_vars = device_config.get("vars", {})
merged_vars.update(host_vars)  # Overwrites everything
```

---

## Automation Layer

**Purpose**: Core orchestration logic

**Location**: `automation/`

### `device_models.py`

**Purpose**: Pydantic models for device-level intent validation

**Key Models**:

#### `LoopbackIntent`
```python
class LoopbackIntent(BaseModel):
    id: int = Field(ge=0, le=2147483647)
    ipv4: str = Field(pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    netmask: str
    description: str | None = Field(max_length=240)
    
    @field_validator("netmask")
    def validate_netmask(cls, v):
        # Validates against list of valid masks
    
    @field_validator("ipv4")
    def validate_ipv4(cls, v):
        # Validates IP format and ranges
```

**Validation**:
- IP address format and valid ranges (no 0.x.x.x or 224.x.x.x+)
- Netmask must be valid dotted-decimal
- Description max 240 chars, no special characters

#### `BGPNeighborIntent`
```python
class BGPNeighborIntent(BaseModel):
    ip: str
    remote_asn: int = Field(ge=1, le=4294967295)
    description: str | None = Field(max_length=80)
    update_source: str | None
```

#### `BGPIntent`
```python
class BGPIntent(BaseModel):
    asn: int = Field(ge=1, le=4294967295)
    router_id: str | None
    neighbors: list[BGPNeighborIntent] = Field(default_factory=list)
```

#### `DeviceIntent`
```python
class DeviceIntent(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    device_type: Literal["ios", "ios-xe", "ios-xr", "nxos"]
    loopbacks: list[LoopbackIntent] = Field(default_factory=list)
    bgp: BGPIntent | None = None
    
    # Deletion control
    delete_unmanaged_loopbacks: bool = False
    delete_unmanaged_bgp_neighbors: bool = False
    
    @field_validator("name")
    def validate_hostname(cls, v):
        # Only alphanumeric, hyphens, underscores
```

**Key Feature**: Deletion flags control behavior per-device

#### `NetworkIntent`
```python
class NetworkIntent(BaseModel):
    devices: list[DeviceIntent] = Field(min_length=1)
    
    @field_validator("devices")
    def validate_unique_devices(cls, v):
        # Ensures no duplicate device names
    
    def get_device(self, name: str) -> DeviceIntent | None:
        """Helper to find device by name"""
```

**Why Pydantic**:
- Runtime validation (catches errors before deployment)
- Type safety
- Auto-generated error messages
- JSON schema generation
- IDE autocomplete support

---

### `device_engine.py`

**Purpose**: Device-level reconciliation engine (calculates and applies minimal changes)

**Location**: `automation/device_engine.py`

**Key Class**: `DeviceEngine`

#### Constructor
```python
def __init__(self, nso_client: NSOClient, inventory=None):
    self.client = nso_client
    self.inventory = inventory  # For device metadata (types, etc.)
```

#### Core Methods

##### `get_current_loopbacks(device_name) -> dict`
**Purpose**: Query current loopback state from NSO

**Process**:
1. Sync device (get latest config from router)
2. Get full device config via RESTCONF
3. Parse loopback interfaces from config
4. Return dict: `{"100": {"ip": "10.100.100.1", ...}}`

**NSO API Path**:
```
GET /devices/device={name}/config/interface/Loopback
```

##### `calculate_loopback_changes(device_intent) -> list[Change]`
**Purpose**: Calculate diff between desired and actual loopback state

**Algorithm**:
```python
current = get_current_loopbacks(device)
desired = {lb.id: lb for lb in device_intent.loopbacks}

changes = []

# Find creates/updates
for lb_id, desired_lb in desired.items():
    if lb_id not in current:
        changes.append(Change(action="create", ...))
    elif current[lb_id] != desired_lb:
        changes.append(Change(action="update", ...))

# Find deletes (if enabled)
unmanaged = [id for id in current if id not in desired]
if device_intent.delete_unmanaged_loopbacks:
    for lb_id in unmanaged:
        changes.append(Change(action="delete", ...))
else:
    logger.info("Ignoring unmanaged loopbacks (safe mode)")

return changes
```

**Returns**: List of `Change` objects

##### `calculate_bgp_changes(device_intent) -> list[Change]`
**Purpose**: Calculate diff for BGP configuration

**Process**:
1. Convert device BGP intent to service intent format
2. Check if BGP already configured correctly (idempotency)
3. If not configured or different, create change
4. If configured + strict mode, check for unmanaged neighbors

**Idempotency Check**:
```python
service_intent = BGPPeeringServiceIntent(...)  # Convert format
is_configured = check_bgp_configured(client, device, service_intent)

if not is_configured:
    changes.append(Change(action="create", resource="bgp", ...))
```

**Unmanaged Neighbor Detection** (if strict mode):
```python
if device_intent.delete_unmanaged_bgp_neighbors:
    current_neighbors = get_current_bgp_neighbors()
    desired_neighbors = {n.ip for n in intent.neighbors}
    unmanaged = current_neighbors - desired_neighbors
    
    for neighbor_ip in unmanaged:
        changes.append(Change(action="delete", resource="bgp-neighbor", ...))
```

**NSO Data Structure Handling**:
- BGP is returned as a **list** (can have multiple BGP processes)
- Must find the process matching our AS number
- Router-ID is nested: `bgp[0].bgp.router-id`

##### `calculate_changes(intent) -> list[Change]`
**Purpose**: Calculate all changes across all devices and resources

```python
def calculate_changes(self, intent: NetworkIntent) -> list[Change]:
    all_changes = []
    
    for device_intent in intent.devices:
        # Loopbacks
        loopback_changes = self.calculate_loopback_changes(device_intent)
        all_changes.extend(loopback_changes)
        
        # BGP
        bgp_changes = self.calculate_bgp_changes(device_intent)
        all_changes.extend(bgp_changes)
        
        # Future: OSPF, static routes, etc.
    
    return all_changes
```

##### `apply_change(change, dry_run) -> bool`
**Purpose**: Execute a single change

**Implementation**:
```python
def apply_change(self, change: Change, dry_run: bool) -> bool:
    if dry_run:
        logger.info(f"[DRY-RUN] Would apply: {change}")
        return True
    
    if change.resource_type == "loopback":
        if change.action in ("create", "update"):
            return self.client.configure_loopback(...)
        elif change.action == "delete":
            return self.client.delete_loopback(...)
    
    elif change.resource_type == "bgp":
        if change.action in ("create", "update"):
            # Convert back to service intent format
            service_intent = BGPPeeringServiceIntent(...)
            success, msg = deploy_bgp_service(self.client, ...)
            return success
        elif change.action == "delete":
            success, msg = remove_bgp_service(...)
            return success
    
    elif change.resource_type == "bgp-neighbor":
        if change.action == "delete":
            # Delete specific neighbor via NSO API
            url = f".../bgp={as_no}/neighbor={neighbor_ip}"
            resp = self.client._safe_delete(url)
            return resp.status_code in (200, 204)
```

##### `apply_intent(intent, dry_run) -> tuple[int, int]`
**Purpose**: Main orchestration method

**Process**:
```python
def apply_intent(self, intent: NetworkIntent, dry_run: bool):
    # 1. Calculate all changes
    changes = self.calculate_changes(intent)
    
    if not changes:
        logger.info("✓ No changes needed")
        return 0, 0
    
    # 2. Show summary
    logger.info(f"Planned changes: {len(changes)} total")
    
    # 3. Apply each change
    success_count = 0
    failure_count = 0
    
    for change in changes:
        if self.apply_change(change, dry_run):
            success_count += 1
        else:
            failure_count += 1
    
    # 4. Summary
    logger.info(f"Complete: {success_count} succeeded, {failure_count} failed")
    
    return success_count, failure_count
```

**Returns**: `(successful_changes, failed_changes)`

---

### `nso_client.py`

**Purpose**: NSO RESTCONF API client with safe operations

**Location**: `automation/nso_client.py`

**Key Class**: `NSOClient`

#### Constructor
```python
def __init__(self, host, port=8080, username="developer", 
             password="C1sco12345", verify_ssl=False, use_https=False, timeout=30.0):
    protocol = "https" if use_https else "http"
    self.base_url = f"{protocol}://{host}:{port}/restconf"
    self.auth = (username, password)
    
    # httpx client with default headers
    self.client = httpx.Client(
        verify=verify_ssl,
        headers={
            "Content-Type": "application/yang-data+json",
            "Accept": "application/yang-data+json",
        },
        timeout=timeout,
    )
```

**Why httpx (not requests)**:
- Modern async support
- HTTP/2 support
- Better type hints
- Connection pooling

#### Safe HTTP Methods

##### `_safe_get(url) -> dict | None`
**Purpose**: GET request with error handling

```python
def _safe_get(self, url):
    try:
        logger.debug(f"GET {url}")
        resp = self.client.get(url, auth=self.auth)
        resp.raise_for_status()
        
        if resp.status_code == 204:
            return {}
        
        return resp.json()
    
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        return None
    except httpx.TimeoutException:
        logger.error("Timeout")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request failed: {e}")
        return None
```

**Why "Safe"**: Never raises exceptions, always returns None on error

##### `_safe_post(url, payload, content_type) -> httpx.Response | None`
**Purpose**: POST request with XML or JSON support

```python
def _safe_post(self, url, payload, content_type=None):
    if isinstance(payload, str) and content_type:
        # XML payload
        headers = {"Content-Type": content_type, "Accept": "application/yang-data+json"}
        resp = self.client.post(url, content=payload, auth=self.auth, headers=headers)
    else:
        # JSON payload
        resp = self.client.post(url, json=payload, auth=self.auth)
    
    resp.raise_for_status()
    return resp
```

##### `_safe_delete(url) -> httpx.Response | None`
**Purpose**: DELETE request

#### High-Level Operations

##### `health_check() -> bool`
**Purpose**: Verify NSO is reachable

```python
def health_check(self):
    url = f"{self.base_url}/data/tailf-ncs:devices"
    result = self._safe_get(url)
    
    if result:
        logger.info("✓ NSO health check passed")
        return True
    else:
        logger.error("✗ NSO health check failed")
        return False
```

##### `get_devices() -> list[str]`
**Purpose**: Get list of managed devices

```python
url = f"{self.base_url}/data/tailf-ncs:devices/device"
result = self._safe_get(url)

devices = [d["name"] for d in result["tailf-ncs:device"]]
return devices
```

##### `sync_from_device(device_name) -> bool`
**Purpose**: Sync config from device to NSO CDB

```python
url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/sync-from"
payload = {"input": {}}

resp = self._safe_post(url, payload)
return resp.status_code in (200, 204)
```

**Why Important**: Must sync before querying config to get latest state

##### `get_device_config(device_name) -> dict`
**Purpose**: Get full device configuration from NSO

```python
url = f"{self.base_url}/data/tailf-ncs:devices/device={device_name}/config"
return self._safe_get(url)
```

**Returns**: Full config tree (can be large!)

##### `configure_loopback(...) -> bool`
**Purpose**: Configure loopback interface

**Parameters**:
- `device_name`, `loopback_id`, `ip_address`, `netmask`, `description`, `dry_run`

**Process**:
```python
# Build XML payload
xml_payload = f"""
<Loopback>
    <name>{loopback_id}</name>
    <description>{description}</description>
    <ip>
        <address>
            <primary>
                <address>{ip_address}</address>
                <mask>{netmask}</mask>
            </primary>
        </address>
    </ip>
</Loopback>
"""

# POST to NSO
url = f"{self.base_url}/data/.../interface"
if dry_run:
    url += "?dry-run=native"

resp = self._safe_post(url, xml_payload, content_type="application/yang-data+xml")
return resp.status_code in (200, 201, 204)
```

##### `delete_loopback(device_name, loopback_id) -> bool`
**Purpose**: Delete loopback interface

```python
url = f"{self.base_url}/data/.../interface/Loopback={loopback_id}"
resp = self._safe_delete(url)
return resp.status_code in (200, 204)
```

##### `rollback(rollback_id, use_fixed_number) -> bool`
**Purpose**: Rollback to previous configuration

**Two modes**:
- Relative ID: `rollback(0)` = most recent, `rollback(1)` = second most recent
- Fixed number: `rollback(10042, use_fixed_number=True)` = specific rollback file

```python
id_element = "fixed-number" if use_fixed_number else "id"
xml_payload = f"""
<input xmlns="http://tail-f.com/ns/rollback">
    <{id_element}>{rollback_id}</{id_element}>
</input>
"""

url = f"{self.base_url}/data/tailf-rollback:rollback-files/apply-rollback-file"
resp = self._safe_post(url, xml_payload, content_type="application/yang-data+xml")
```

---

### `service_models.py`

**Purpose**: Pydantic models for service-level intent (future use)

**Location**: `automation/service_models.py`

**Why Separate from device_models.py**:
- Device models: Per-device unique configs (BGP with unique router-IDs)
- Service models: Same config across devices (L3VPN with same VRF)

**Key Models**:

#### `BGPNeighborIntent` (Service version)
```python
class BGPNeighborIntent(BaseModel):
    neighbor_ip: str  # ← Note: different field name from device model!
    remote_as: int    # ← device model uses "remote_asn"
    description: str | None
    password: str | None
    update_source: str | None
```

**Field Name Mismatch**: This caused the bug we fixed! Device model uses `ip`/`remote_asn`, service model uses `neighbor_ip`/`remote_as`.

#### `BGPPeeringServiceIntent`
```python
class BGPPeeringServiceIntent(BaseModel):
    service_name: str = "bgp-peering"
    local_as: int
    router_id: str
    neighbors: list[BGPNeighborIntent]
    import_policy: str | None
    export_policy: str | None
```

**Used By**: `services/bgp_peering.py` for actual deployment

#### `ServiceDeploymentIntent`
```python
class ServiceDeploymentIntent(BaseModel):
    service_type: Literal["bgp-peering", "ospf", "loopback"]
    target_devices: list[str]
    bgp_config: BGPPeeringServiceIntent | None
```

**Future Use**: When building true services (L3VPN, etc.)

---

### `service_orchestrator.py`

**Purpose**: Multi-device service deployment with parallel execution

**Location**: `automation/service_orchestrator.py`

**Key Class**: `ServiceOrchestrator`

**Note**: Currently not used for BGP (we use device_engine instead), but kept for future true services.

#### Key Methods

##### `deploy_service(intent, dry_run, parallel) -> list[ServiceDeploymentResult]`
**Purpose**: Deploy service to multiple devices

**Features**:
- Parallel execution with ThreadPoolExecutor
- Progress tracking
- Result collection per device

```python
def deploy_service(self, intent, dry_run=False, parallel=True):
    if parallel and len(intent.target_devices) > 1:
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_device = {
                executor.submit(self._deploy_to_device, device, intent, dry_run): device
                for device in intent.target_devices
            }
            
            for future in as_completed(future_to_device):
                result = future.result()
                results.append(result)
    else:
        # Sequential deployment
        for device in intent.target_devices:
            result = self._deploy_to_device(device, intent, dry_run)
            results.append(result)
    
    return results
```

##### `get_service_targets(**filters) -> list[str]`
**Purpose**: Get devices from inventory for dynamic targeting

```python
# Get all distribution routers
targets = orchestrator.get_service_targets(group="distribution")

# Get IOS-XE devices in west region
targets = orchestrator.get_service_targets(device_type="ios-xe", region="west")
```

**Future Use**: Service-level VPN deployment across many devices

---

### `template_renderer.py`

**Purpose**: Jinja2 template rendering for device configs

**Location**: `automation/template_renderer.py`

**Key Class**: `TemplateRenderer`

#### Constructor
```python
def __init__(self, template_dir=None):
    if template_dir is None:
        template_dir = Path(__file__).parent.parent / "templates"
    
    self.env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,  # Fail if variable missing
        trim_blocks=True,           # Clean whitespace
        lstrip_blocks=True,
        autoescape=False,           # Don't escape XML
    )
```

**Key Settings**:
- `StrictUndefined`: Fails immediately if template uses undefined variable (better than silent errors)
- `trim_blocks`/`lstrip_blocks`: Removes extra whitespace from templates
- `autoescape=False`: Don't escape XML/HTML (we want raw XML output)

#### Methods

##### `render(template_name, **context) -> str`
**Purpose**: Render template with variables

```python
def render(self, template_name, **context):
    template = self.env.get_template(template_name)
    rendered = template.render(**context)
    return rendered
```

**Example**:
```python
renderer = TemplateRenderer()
xml = renderer.render(
    "ios-xe/bgp_service.xml.j2",
    local_as=65001,
    router_id="10.100.100.1",
    neighbors=[{"neighbor_ip": "10.0.0.2", "remote_as": 65002}]
)
```

##### `validate_template(template_name, **sample_context) -> bool`
**Purpose**: Test template with sample data

```python
def validate_template(self, template_name, **sample_context):
    try:
        self.render(template_name, **sample_context)
        return True
    except Exception as e:
        logger.error(f"Template validation failed: {e}")
        return False
```

**Use Case**: Catch template errors early in testing

##### Convenience Function: `render_template()`
```python
def render_template(template_name, template_dir=None, **context):
    """One-liner for simple rendering"""
    renderer = TemplateRenderer(template_dir=template_dir)
    return renderer.render(template_name, **context)
```

---

## Services Layer

**Purpose**: Reusable deployment functions (HOW to deploy)

**Location**: `services/`

### `bgp_peering.py`

**Purpose**: BGP-specific deployment logic

**Location**: `services/bgp_peering.py`

**Key Functions**:

#### `check_bgp_configured(client, device_name, intent) -> bool`
**Purpose**: Idempotency check - is BGP already configured correctly?

**Algorithm**:
```python
def check_bgp_configured(client, device_name, intent):
    # 1. Sync device
    client.sync_from_device(device_name)
    
    # 2. Get current config
    config = client.get_device_config(device_name)
    
    # 3. Extract BGP config
    bgp_config = config["tailf-ncs:config"]["tailf-ned-cisco-ios:router"]["bgp"]
    
    # 4. Handle BGP as list (can have multiple processes)
    if not isinstance(bgp_config, list):
        bgp_config = [bgp_config]
    
    # 5. Find process matching our AS
    bgp_process = None
    for process in bgp_config:
        if str(process.get("as-no")) == str(intent.local_as):
            bgp_process = process
            break
    
    if not bgp_process:
        return False  # BGP not configured
    
    # 6. Check router-ID (nested: bgp.bgp.router-id)
    bgp_sub = bgp_process.get("bgp", {})
    current_router_id = bgp_sub.get("router-id")
    if current_router_id != intent.router_id:
        return False
    
    # 7. Check neighbors
    current_neighbors = bgp_process.get("neighbor", [])
    if not isinstance(current_neighbors, list):
        current_neighbors = [current_neighbors] if current_neighbors else []
    
    current_neighbor_ips = {n.get("id") for n in current_neighbors}
    desired_neighbor_ips = {n.neighbor_ip for n in intent.neighbors}
    
    if current_neighbor_ips != desired_neighbor_ips:
        return False
    
    # All checks passed!
    return True
```

**Why Complex**: NSO returns BGP as a list, router-ID is nested, neighbors can be dict or list

**Returns**: `True` if BGP matches intent (skip deployment), `False` if changes needed

#### `deploy_bgp_service(...) -> tuple[bool, str]`
**Purpose**: Deploy BGP configuration to device

**Parameters**:
```python
def deploy_bgp_service(
    client: NSOClient,
    device_name: str,
    intent: BGPPeeringServiceIntent,
    dry_run: bool = False,
    inventory = None
) -> tuple[bool, str]:
```

**Process**:
```python
def deploy_bgp_service(client, device_name, intent, dry_run, inventory):
    # 1. Get device metadata from inventory
    device = inventory.get_device(device_name)
    
    # 2. Idempotency check
    if not dry_run:
        if check_bgp_configured(client, device_name, intent):
            return True, "Already configured (no changes needed)"
    
    # 3. Select template based on device type
    if device.device_type == "ios-xr":
        template_name = "ios-xr/bgp_service.xml.j2"
    else:
        template_name = "ios-xe/bgp_service.xml.j2"
    
    # 4. Render template
    config_xml = render_template(
        template_name,
        local_as=intent.local_as,
        router_id=intent.router_id,
        neighbors=[n.model_dump() for n in intent.neighbors],
        import_policy=intent.import_policy,
        export_policy=intent.export_policy
    )
    
    # 5. Dry-run mode
    if dry_run:
        artifact_file = Path("artifacts") / f"{device_name}_bgp_service.xml"
        artifact_file.write_text(config_xml)
        return True, f"DRY-RUN: Saved to {artifact_file}"
    
    # 6. Build NSO URL based on device type
    if device.device_type == "ios-xr":
        url = f"{client.base_url}/data/.../router/bgp"
    else:
        url = f"{client.base_url}/data/.../router"
    
    # 7. POST to NSO
    resp = client._safe_post(url, config_xml, content_type="application/yang-data+xml")
    
    if resp and resp.status_code in (200, 201, 204):
        return True, "BGP service deployed successfully"
    else:
        return False, "BGP deployment failed"
```

**Returns**: `(success: bool, message: str)`

**Key Design Points**:
- Idempotency built-in (checks before deploying)
- Template selection based on device type
- Dry-run support (saves artifacts)
- Proper error handling

#### `remove_bgp_service(client, device_name, local_as, dry_run) -> tuple[bool, str]`
**Purpose**: Remove BGP configuration

```python
def remove_bgp_service(client, device_name, local_as, dry_run):
    if dry_run:
        return True, f"DRY-RUN: Would remove BGP AS {local_as}"
    
    url = f"{client.base_url}/data/.../router/bgp={local_as}"
    resp = client._safe_delete(url)
    
    if resp and resp.status_code in (200, 204):
        return True, "BGP service removed successfully"
    else:
        return False, "BGP removal failed"
```

---

## Templates

**Purpose**: Jinja2 templates for device configurations

**Location**: `templates/`

### `ios-xe/bgp_service.xml.j2`

**Purpose**: BGP configuration template for IOS-XE devices

**Structure**:
```xml
<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <router xmlns="urn:ios">
    <bgp>
      <as-no>{{ local_as }}</as-no>
      <bgp>
        <router-id>{{ router_id }}</router-id>
      </bgp>
      {% for neighbor in neighbors %}
      <neighbor>
        <id>{{ neighbor.neighbor_ip }}</id>
        <remote-as>{{ neighbor.remote_as }}</remote-as>
        {% if neighbor.description %}
        <description>{{ neighbor.description }}</description>
        {% endif %}
        {% if neighbor.password %}
        <password>
          <encryption>0</encryption>
          <string>{{ neighbor.password }}</string>
        </password>
        {% endif %}
        {% if neighbor.update_source %}
        <update-source>
          <Loopback>{{ neighbor.update_source.replace('Loopback', '') }}</Loopback>
        </update-source>
        {% endif %}
      </neighbor>
      {% endfor %}
      {% if import_policy %}
      <address-family>
        <ipv4>
          <af>unicast</af>
          <route-map>
            <inbound>{{ import_policy }}</inbound>
          </route-map>
        </ipv4>
      </address-family>
      {% endif %}
    </bgp>
  </router>
</config>
```

**Key Features**:
- NETCONF wrapper (`<config>` with namespace)
- Conditional blocks (`{% if %}`) for optional fields
- Loop over neighbors (`{% for %}`)
- String manipulation (`replace('Loopback', '')`)

**Variables Required**:
- `local_as` (int)
- `router_id` (str)
- `neighbors` (list of dicts)
- `import_policy` (str, optional)
- `export_policy` (str, optional)

### `ios-xr/bgp_service.xml.j2`

**Purpose**: BGP configuration template for IOS-XR devices

**Differences from IOS-XE**:
- Different XML namespace
- Different BGP structure
- Different neighbor configuration syntax

**Note**: Currently similar structure, but would diverge for advanced features

---

## Scripts

**Purpose**: CLI tools for operators

**Location**: `scripts/`

### `apply_device_intent.py`

**Purpose**: Main deployment script for device-level configurations

**Location**: `scripts/apply_device_intent.py`

**Usage**:
```bash
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run \
  --verbose
```

**Key Functions**:

#### `load_device_intent(intent_file) -> NetworkIntent`
**Purpose**: Load and validate YAML file

```python
def load_device_intent(intent_file):
    with open(intent_file) as f:
        intent_data = yaml.safe_load(f)
    
    # Validate with Pydantic
    intent = NetworkIntent(**intent_data)
    
    return intent
```

**Raises**: `ValidationError` if intent is invalid

#### `merge_intents(intents) -> NetworkIntent`
**Purpose**: Intelligently merge multiple intent files

**Algorithm** (FIXED VERSION):
```python
def merge_intents(intents):
    device_map = {}
    
    for intent in intents:
        for device in intent.devices:
            if device.name in device_map:
                existing = device_map[device.name]
                
                # Merge loopbacks (combine, last wins for duplicates)
                merged_loopbacks = list(existing.loopbacks)
                for new_lb in device.loopbacks:
                    if new_lb.id in existing_lb_ids:
                        # Replace
                        merged_loopbacks = [lb for lb in merged_loopbacks if lb.id != new_lb.id]
                    merged_loopbacks.append(new_lb)
                
                # BGP: use latest if provided
                merged_bgp = device.bgp if device.bgp else existing.bgp
                
                # Create merged device
                merged_device = DeviceIntent(
                    name=device.name,
                    device_type=device.device_type,
                    loopbacks=merged_loopbacks,
                    bgp=merged_bgp,
                    delete_unmanaged_loopbacks=device.delete_unmanaged_loopbacks,
                    delete_unmanaged_bgp_neighbors=device.delete_unmanaged_bgp_neighbors,
                )
                
                device_map[device.name] = merged_device
            else:
                device_map[device.name] = device
    
    return NetworkIntent(devices=list(device_map.values()))
```

**Key Feature**: Combines resources instead of replacing entire device

#### `filter_intent_by_device(intent, device_name) -> NetworkIntent`
**Purpose**: Filter to single device

```python
def filter_intent_by_device(intent, device_name):
    device = intent.get_device(device_name)
    if not device:
        raise ValueError(f"Device '{device_name}' not found in intent")
    
    return NetworkIntent(devices=[device])
```

#### `main()`
**Purpose**: Main entry point with argument parsing

**Process**:
1. Parse command-line arguments
2. Load intent file(s)
3. Merge if multiple files
4. Filter by device if specified
5. Show intent summary
6. Initialize NSO client
7. Load inventory
8. Initialize device engine
9. Apply intent
10. Show results

**Arguments**:
- `--intent` (required, can specify multiple times)
- `--device` (optional, filter to one device)
- `--dry-run` (optional, preview only)
- `--verbose` (optional, debug logging)
- `--nso-host` (optional, default from env)
- `--nso-port` (optional, default from env)

**Exit Codes**:
- `0`: Success
- `1`: Failure or validation error

---

### `deploy_service.py`

**Purpose**: Service-level deployment (future use)

**Location**: `scripts/deploy_service.py`

**Status**: Exists but not currently used (BGP uses device_engine instead)

**Future Use**: Deploy services like L3VPN where config is identical across devices

---

### `sync_devices.py`

**Purpose**: Sync all devices from NSO

**Usage**:
```bash
python scripts/sync_devices.py
```

**Process**:
```python
client = NSOClient(...)
devices = client.get_devices()

for device in devices:
    success = client.sync_from_device(device)
    print(f"{'✓' if success else '✗'} {device}")
```

---

### `run_any_command.py`

**Purpose**: Execute arbitrary NSO operations

**Usage**:
```bash
python scripts/run_any_command.py \
  --device dist-rtr01 \
  --command "show ip bgp summary"
```

**Note**: For ad-hoc operations and debugging

---

## Tests

**Purpose**: Comprehensive test coverage

**Location**: `tests/`

### `conftest.py`

**Purpose**: Pytest fixtures and configuration

**Location**: `tests/conftest.py`

**Key Fixtures**:

#### Session-Scoped (Shared across all tests)
```python
@pytest.fixture(scope="session")
def nso_credentials():
    """NSO connection details from environment"""

@pytest.fixture(scope="session")
def nso_client_session(nso_credentials):
    """Shared NSO client for read-only operations"""

@pytest.fixture(scope="session")
def available_devices(nso_client_session):
    """Discover devices from NSO"""

@pytest.fixture(scope="session")
def inventory():
    """Load inventory once"""

@pytest.fixture(scope="session")
def template_renderer():
    """Template renderer"""
```

#### Function-Scoped (Fresh for each test)
```python
@pytest.fixture(scope="function")
def nso_client(nso_credentials):
    """Fresh NSO client for write operations"""

@pytest.fixture(scope="function")
def test_device(available_devices):
    """Single IOS-XE device for testing"""

@pytest.fixture(scope="function")
def sync_device(nso_client, test_device):
    """Test device with pre-test sync"""

@pytest.fixture(scope="function")
def service_orchestrator(nso_client, inventory):
    """Service orchestrator with NSO + inventory"""
```

#### Cleanup Fixtures
```python
@pytest.fixture(scope="function")
def clean_bgp_service(nso_client, test_device):
    """Auto-cleanup BGP after test"""
    deployed_as_numbers = []
    
    class BGPCleaner:
        @staticmethod
        def register(as_number):
            deployed_as_numbers.append(as_number)
    
    yield BGPCleaner()
    
    # Cleanup after test
    for as_number in deployed_as_numbers:
        remove_bgp_service(nso_client, test_device, as_number)
```

**Usage**:
```python
def test_bgp(nso_client, test_device, clean_bgp_service):
    clean_bgp_service.register(65099)
    # Deploy BGP...
    # Auto-cleanup happens after test
```

#### Auto-Markers
```python
def pytest_collection_modifyitems(config, items):
    """Automatically mark tests"""
    for item in items:
        if "nso_client" in str(item.fixturenames):
            item.add_marker(pytest.mark.nso)
        if "service" in item.nodeid.lower():
            item.add_marker(pytest.mark.service)
```

**Result**: Tests auto-tagged with `@pytest.mark.nso`, `@pytest.mark.service`, etc.

---

### Test Files

#### `test_device_models.py`
**Purpose**: Unit tests for Pydantic models

**Tests**:
- Valid loopback/BGP configurations
- Invalid netmasks rejected
- Invalid IP addresses rejected
- Duplicate device names rejected
- Deletion flags work correctly

**Example**:
```python
def test_invalid_loopback_netmask():
    with pytest.raises(ValidationError):
        LoopbackIntent(
            id=100,
            ipv4="10.100.100.1",
            netmask="255.255.255.256",  # Invalid!
        )
```

#### `test_device_bgp.py`
**Purpose**: BGP deployment tests

**Test Classes**:
- `TestDeviceLevelBGP`: Basic BGP deployment
- `TestBGPNeighborDeletion`: Safe vs strict deletion
- Unit tests for deletion flags

**Key Tests**:
```python
def test_deploy_device_bgp_full_cycle():
    """Deploy → Verify → Test Idempotency → Remove"""
    
def test_safe_mode_leaves_extra_neighbors():
    """Verify safe mode preserves unmanaged neighbors"""
    
def test_strict_mode_deletes_extra_neighbors():
    """Verify strict mode removes unmanaged neighbors"""
```

#### `test_nso_loopback.py`
**Purpose**: Loopback deployment tests

**Tests**:
- Create loopback
- Create multiple loopbacks
- Dry-run mode
- Rollback functionality
- Delete loopback

#### `test_template_renderer.py`
**Purpose**: Template rendering tests

**Tests**:
- Render BGP template
- Optional fields handled correctly
- Missing variables raise errors
- Template not found raises error
- Multiple neighbors rendered correctly

---

## Design Patterns

### 1. Intent-Based Configuration

**Pattern**: Declare desired state, framework calculates diff

**Implementation**:
```python
# User declares intent
intent = {
    "devices": [{
        "name": "rtr01",
        "bgp": {"asn": 65001, "router_id": "10.1.1.1"}
    }]
}

# Framework calculates diff
current_state = get_current_bgp(device)
desired_state = intent.bgp
changes = calculate_diff(current, desired)

# Framework applies minimal changes
apply_changes(changes)
```

**Benefits**:
- Declarative (what, not how)
- Idempotent
- Predictable
- Self-documenting

### 2. Device-Level vs Service-Level

**Device-Level** (This Project):
```yaml
# Each device unique
devices:
  - name: rtr01
    bgp:
      router_id: 10.1.1.1  # Unique!
  - name: rtr02
    bgp:
      router_id: 10.2.2.2  # Different!
```

**Service-Level** (Future):
```yaml
# Same config everywhere
service_type: l3vpn
target_devices: [rtr01, rtr02, rtr03]
vrf_config:
  name: CUSTOMER_A  # Same on all devices
  rd: "65001:100"
```

**When to Use Each**:
- Device-level: BGP, interfaces, device-specific configs
- Service-level: VPN, VRF, QoS policies, multicast

### 3. Safe Getter Pattern

**Pattern**: HTTP methods never raise exceptions

**Implementation**:
```python
def _safe_get(self, url):
    try:
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error: {e}")
        return None  # Always returns, never raises
```

**Benefits**:
- No try/except needed in calling code
- Errors logged automatically
- Caller checks for None

### 4. Template-Based Configuration

**Pattern**: Separate logic from config syntax

**Implementation**:
```python
# Logic
config_data = {
    "local_as": 65001,
    "neighbors": [...]
}

# Template (syntax)
template = """
<bgp>
  <as-no>{{ local_as }}</as-no>
  {% for n in neighbors %}
  <neighbor>...</neighbor>
  {% endfor %}
</bgp>
"""

# Render
xml = render_template(template, **config_data)
```

**Benefits**:
- Easy to support multiple platforms (IOS-XE, IOS-XR, NX-OS)
- Logic separate from syntax
- Templates testable independently

### 5. Reconciliation Engine

**Pattern**: Calculate minimal diff, apply only necessary changes

**Implementation**:
```python
class DeviceEngine:
    def calculate_changes(self, intent):
        current = get_current_state()
        desired = intent
        
        changes = []
        for resource in desired:
            if resource not in current:
                changes.append(Change(action="create", ...))
            elif current[resource] != desired[resource]:
                changes.append(Change(action="update", ...))
        
        return changes
```

**Benefits**:
- Minimal disruption (only change what's needed)
- Predictable (know what will change before applying)
- Efficient (no unnecessary API calls)

### 6. Inventory with Variable Inheritance

**Pattern**: DRY principle for device variables

**Implementation**:
```
defaults.yaml     → nso_host: 10.10.20.49
groups.yaml       → distribution: bgp_as: 65001
hosts.yaml        → dist-rtr01: loopback0_ip: 10.100.100.1

Result for dist-rtr01:
  nso_host: 10.10.20.49        (from defaults)
  bgp_as: 65001                 (from group)
  loopback0_ip: 10.100.100.1   (from host)
```

**Benefits**:
- No config duplication
- Easy to change org-wide settings
- Per-device overrides available

---

## Data Flow

### Example: BGP Deployment

```
1. YAML Intent File (device_bgp_configs.yaml)
   ↓
2. apply_device_intent.py loads & validates
   ↓
3. Pydantic models validate structure
   ↓
4. device_engine.py calculates changes
   ├─→ Queries NSO for current BGP config
   ├─→ Compares with desired state
   └─→ Returns list of Change objects
   ↓
5. device_engine.py applies changes
   ├─→ For each change:
   │   ├─→ Converts to service intent format
   │   ├─→ Calls deploy_bgp_service()
   │   │   ├─→ Gets device type from inventory
   │   │   ├─→ Selects template (ios-xe vs ios-xr)
   │   │   ├─→ Renders template with Jinja2
   │   │   └─→ POSTs XML to NSO RESTCONF API
   │   └─→ Returns success/failure
   └─→ Collects results
   ↓
6. Summary displayed to user
   "Intent reconciliation complete: X succeeded, Y failed"
```

### Data Transformations

**1. YAML → Pydantic Models**:
```yaml
# device_bgp_configs.yaml
bgp:
  asn: 65001
  router_id: "10.1.1.1"
```
↓
```python
# DeviceIntent (device_models.py)
BGPIntent(
    asn=65001,
    router_id="10.1.1.1",
    neighbors=[BGPNeighborIntent(...)]
)
```

**2. Device Model → Service Model**:
```python
# device_models.BGPNeighborIntent
BGPNeighborIntent(
    ip="10.0.0.2",           # ← Field name: "ip"
    remote_asn=65002         # ← Field name: "remote_asn"
)
```
↓
```python
# service_models.BGPNeighborIntent
BGPNeighborIntent(
    neighbor_ip="10.0.0.2",  # ← Field name: "neighbor_ip"
    remote_as=65002          # ← Field name: "remote_as"
)
```

**3. Service Model → Template Variables**:
```python
BGPPeeringServiceIntent(
    local_as=65001,
    router_id="10.1.1.1",
    neighbors=[...]
)
```
↓
```python
{
    "local_as": 65001,
    "router_id": "10.1.1.1",
    "neighbors": [{"neighbor_ip": "10.0.0.2", ...}]
}
```

**4. Template → XML**:
```jinja2
<bgp>
  <as-no>{{ local_as }}</as-no>
  <bgp>
    <router-id>{{ router_id }}</router-id>
  </bgp>
</bgp>
```
↓
```xml
<bgp>
  <as-no>65001</as-no>
  <bgp>
    <router-id>10.1.1.1</router-id>
  </bgp>
</bgp>
```

**5. XML → NSO RESTCONF API**:
```http
POST /restconf/data/.../router
Content-Type: application/yang-data+xml

<config xmlns="...">
  <router xmlns="urn:ios">
    <bgp>...</bgp>
  </router>
</config>
```
↓
```
NSO applies config to device via NETCONF
```

---

## Summary

This architecture provides:

✅ **Clean separation of concerns** - Each layer has specific responsibility  
✅ **Reusability** - Services used by multiple orchestrators  
✅ **Testability** - Each component independently testable  
✅ **Idempotency** - Safe to run repeatedly  
✅ **Flexibility** - Easy to add new resources (OSPF, interfaces, etc.)  
✅ **Production-ready** - Comprehensive error handling, logging, validation  

**Next**: See [WORKFLOW.md](WORKFLOW.md) for detailed process flows and examples.