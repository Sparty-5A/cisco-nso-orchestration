# WORKFLOW.md - Process Flows and User Journeys

**End-to-end workflows for NSO Network Orchestration Framework**

This document complements [ARCHITECTURE.md](ARCHITECTURE.md) by showing **how to use** the framework through practical workflows, decision trees, and troubleshooting guides.

---

## Table of Contents

- [User Journeys](#user-journeys)
  - [New User: First Deployment](#new-user-first-deployment)
  - [Regular User: Adding a New Device](#regular-user-adding-a-new-device)
  - [Regular User: Modifying BGP Configuration](#regular-user-modifying-bgp-configuration)
  - [Advanced User: Multi-Resource Deployment](#advanced-user-multi-resource-deployment)
- [Detailed Process Flows](#detailed-process-flows)
  - [Flow 1: BGP Deployment from Scratch](#flow-1-bgp-deployment-from-scratch)
  - [Flow 2: Loopback Interface Management](#flow-2-loopback-interface-management)
  - [Flow 3: Intent Merging Workflow](#flow-3-intent-merging-workflow)
  - [Flow 4: Handling Unmanaged Resources](#flow-4-handling-unmanaged-resources)
- [Decision Trees](#decision-trees)
  - [Should I Use Device-Level or Service-Level?](#should-i-use-device-level-or-service-level)
  - [Safe Mode vs Strict Mode](#safe-mode-vs-strict-mode)
  - [When to Use --dry-run](#when-to-use---dry-run)
- [Common Scenarios](#common-scenarios)
  - [Scenario 1: New Router Onboarding](#scenario-1-new-router-onboarding)
  - [Scenario 2: BGP Neighbor Addition](#scenario-2-bgp-neighbor-addition)
  - [Scenario 3: Migrating from Manual to Automation](#scenario-3-migrating-from-manual-to-automation)
  - [Scenario 4: Removing a Device](#scenario-4-removing-a-device)
- [Troubleshooting Guide](#troubleshooting-guide)
  - [NSO Connection Issues](#nso-connection-issues)
  - [Validation Errors](#validation-errors)
  - [Deployment Failures](#deployment-failures)
  - [Idempotency Issues](#idempotency-issues)
- [Development Workflows](#development-workflows)
  - [Adding a New Resource Type](#adding-a-new-resource-type)
  - [Adding Support for New Device Type](#adding-support-for-new-device-type)
  - [Testing New Features](#testing-new-features)

---

## User Journeys

### New User: First Deployment

**Goal**: Deploy BGP configuration to a development device for the first time

**Prerequisites**:
- NSO sandbox access
- Python 3.12+ installed
- Repository cloned

**Journey**:

```bash
# Step 1: Setup environment
cd nso_orchestration
pip install -r requirements.txt

# Step 2: Configure NSO connection (optional - has defaults)
export NSO_HOST=10.10.20.49
export NSO_USER=developer
export NSO_PW=C1sco12345

# Step 3: Verify NSO connectivity
python scripts/sync_devices.py

# Step 4: Review the intent file (understand what will be deployed)
cat intent/device_bgp_configs.yaml

# Step 5: DRY-RUN first (always!)
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run \
  --verbose

# Step 6: Review the output carefully
# Look for:
# - "Planned changes: X total"
# - "Would apply" messages
# - No errors

# Step 7: Deploy for real
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01

# Step 8: Verify idempotency (should show no changes)
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01

# Expected: "✓ No changes needed - network is in desired state"
```

**Success Criteria**:
- ✅ BGP deployed without errors
- ✅ Second run shows "no changes needed"
- ✅ BGP session established (verify with `show ip bgp summary` on device)

**Common First-Time Issues**:
- **NSO unreachable**: Check VPN connection and NSO_HOST
- **Device not synced**: Run `sync_devices.py` first
- **Validation errors**: Check YAML syntax and required fields

---

### Regular User: Adding a New Device

**Goal**: Add a new router to the managed inventory and deploy configs

**Journey**:

```bash
# Step 1: Add device to inventory
vim inventory/hosts.yaml
```

```yaml
# Add new entry
new-rtr01:
  hostname: new-rtr01
  ip_address: 10.10.20.190
  device_type: ios-xe
  protocol: ssh
  groups:
    - distribution
    - router
    - production
  vars:
    loopback0_ip: 10.100.100.99
    bgp_router_id: 10.100.100.99
    bgp_as: 65001
```

```bash
# Step 2: Validate inventory
python -c "
from nso_orchestration.automation.inventory_loader import load_inventory
inv = load_inventory()
is_valid, issues = inv.validate()
print('✓ Valid' if is_valid else f'✗ Issues: {issues}')
print(f'Found device: {inv.get_device(\"new-rtr01\")}')
"

# Step 3: Add device to intent files
vim intent/device_loopbacks.yaml
```

```yaml
# Add loopback config
devices:
  - name: new-rtr01
    device_type: ios-xe
    delete_unmanaged_loopbacks: false
    loopbacks:
      - id: 100
        ipv4: 10.100.100.99
        netmask: 255.255.255.255
        description: "Management loopback"
```

```bash
vim intent/device_bgp_configs.yaml
```

```yaml
# Add BGP config
devices:
  - name: new-rtr01
    device_type: ios-xe
    delete_unmanaged_bgp_neighbors: false
    bgp:
      asn: 65001
      router_id: 10.100.100.99
      neighbors:
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01"
          update_source: "Loopback0"
```

```bash
# Step 4: Deploy to new device
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device new-rtr01 \
  --dry-run

# Step 5: Review and apply
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device new-rtr01
```

**Success Criteria**:
- ✅ Device appears in inventory
- ✅ Intent files validated
- ✅ Configs deployed successfully
- ✅ BGP neighbors established

---

### Regular User: Modifying BGP Configuration

**Goal**: Add a new BGP neighbor to existing configuration

**Journey**:

```bash
# Step 1: Check current state
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run

# Expected: "No changes needed"

# Step 2: Modify intent file
vim intent/device_bgp_configs.yaml
```

```yaml
# Add new neighbor to dist-rtr01
devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_bgp_neighbors: false
    bgp:
      asn: 65001
      router_id: 10.100.100.1
      neighbors:
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01"
          update_source: "Loopback0"
        # NEW NEIGHBOR ADDED
        - ip: 10.200.200.2
          remote_asn: 65001
          description: "iBGP to dev-core-rtr01"
          update_source: "Loopback0"
```

```bash
# Step 3: Dry-run to preview changes
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run

# Expected: "1 changes: 1 update"
# Look for: "UPDATE bgp"

# Step 4: Apply changes
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# Step 5: Verify idempotency
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# Expected: "No changes needed"
```

**Success Criteria**:
- ✅ New neighbor added
- ✅ Existing neighbor unchanged (no flap)
- ✅ BGP session established with new neighbor

---

### Advanced User: Multi-Resource Deployment

**Goal**: Deploy loopbacks + BGP + future resources to multiple devices

**Journey**:

```bash
# Step 1: Create comprehensive intent
# Combine multiple resource types in single deployment

python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --dry-run

# Framework will:
# 1. Load both files
# 2. Merge intents intelligently
# 3. Calculate changes for all resources
# 4. Show combined plan

# Step 2: Review the plan
# Look for:
# - Loopback changes per device
# - BGP changes per device
# - Total change count

# Step 3: Deploy everything
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml

# Framework deploys:
# - All loopbacks first
# - Then all BGP configs
# - Per device sequentially (or parallel in future)
```

**Key Feature**: Intent merging ensures:
- Same device in multiple files = configs merged
- Duplicate loopback IDs = last definition wins
- BGP uses latest definition if in multiple files

---

## Detailed Process Flows

### Flow 1: BGP Deployment from Scratch

**Complete end-to-end flow with all internal steps**

```
┌─────────────────────────────────────────────────────────────────┐
│ USER: Edit intent/device_bgp_configs.yaml                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ USER: Run apply_device_intent.py --intent ... --dry-run         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Load YAML file                                          │
│   • Read intent/device_bgp_configs.yaml                         │
│   • Parse YAML → Python dict                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Validate with Pydantic                                  │
│   • NetworkIntent(**yaml_data)                                  │
│   • Validates:                                                  │
│     - Device names unique                                       │
│     - BGP AS numbers valid (1-4294967295)                       │
│     - Router IDs valid IPv4                                     │
│     - Neighbor IPs valid                                        │
│   • Raises ValidationError if invalid                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Initialize NSO Client                                   │
│   • Connect to NSO_HOST:NSO_PORT                                │
│   • Authenticate with NSO_USER:NSO_PW                           │
│   • health_check() verifies connectivity                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Load Inventory                                          │
│   • Load defaults.yaml, groups.yaml, hosts.yaml                 │
│   • Merge variables (defaults → groups → host)                  │
│   • Get device_type for template selection                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Calculate Changes (device_engine.py)                    │
│                                                                  │
│   For each device in intent:                                    │
│     A) Query Current State:                                     │
│        • sync_from_device(device_name)                          │
│        • get_device_config(device_name)                         │
│        • Parse BGP config from JSON                             │
│                                                                  │
│     B) Convert Intent Format:                                   │
│        • device_models.BGPIntent → service_models.BGPService    │
│        • Map field names (ip→neighbor_ip, remote_asn→remote_as) │
│                                                                  │
│     C) Check Idempotency:                                       │
│        • check_bgp_configured(device, intent)                   │
│        • Compare AS, router-ID, neighbor IPs                    │
│        • Return True if matches (skip deployment)               │
│                                                                  │
│     D) Generate Change Objects:                                 │
│        if not configured:                                       │
│          Change(action="create", resource="bgp", ...)           │
│        if delete_unmanaged_neighbors:                           │
│          for unmanaged_neighbor:                                │
│            Change(action="delete", resource="bgp-neighbor", ...)│
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Display Plan (dry-run stops here)                       │
│   • Show summary: "X creates, Y updates, Z deletes"             │
│   • List each change with device name                           │
│   • Exit if --dry-run flag set                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: Apply Changes                                           │
│                                                                  │
│   For each change:                                              │
│     A) Select Template:                                         │
│        • Get device from inventory                              │
│        • if device_type == "ios-xr":                            │
│            template = "ios-xr/bgp_service.xml.j2"               │
│          else:                                                  │
│            template = "ios-xe/bgp_service.xml.j2"               │
│                                                                  │
│     B) Render Template:                                         │
│        • template_renderer.render(template, **intent_vars)      │
│        • Produces XML config                                    │
│                                                                  │
│     C) Build NSO URL:                                           │
│        • if ios-xr: .../router/bgp                              │
│        • if ios-xe: .../router                                  │
│                                                                  │
│     D) POST to NSO:                                             │
│        • nso_client._safe_post(url, xml, content_type="xml")    │
│        • NSO validates and applies to device via NETCONF        │
│                                                                  │
│     E) Record Result:                                           │
│        • success_count++ or failure_count++                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 8: Display Results                                         │
│   • "Intent reconciliation complete: X succeeded, Y failed"     │
│   • Exit code: 0 if all success, 1 if any failures              │
└─────────────────────────────────────────────────────────────────┘
```

**Timeline**: ~10-30 seconds depending on number of devices

**Error Handling at Each Step**:
- Step 1: File not found → exit with error
- Step 2: Validation fails → show detailed Pydantic error
- Step 3: NSO unreachable → exit with connection error
- Step 4: Inventory issues → warn but continue
- Step 5: API errors → logged, change marked as failed
- Step 7: Template errors → logged, change marked as failed

---

### Flow 2: Loopback Interface Management

**Deploying loopback interfaces with deletion policy**

```
┌─────────────────────────────────────────────────────────────────┐
│ SCENARIO: Device has 3 loopbacks (Lo0, Lo100, Lo200)           │
│ INTENT: Deploy Lo100 and Lo300                                  │
│ POLICY: delete_unmanaged_loopbacks = false (safe mode)         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ get_current_loopbacks(device_name)                              │
│   1. sync_from_device()                                         │
│   2. get_device_config()                                        │
│   3. Parse: config.interface.Loopback[]                         │
│   4. Return: {"0": {...}, "100": {...}, "200": {...}}          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ calculate_loopback_changes(device_intent)                       │
│                                                                  │
│ Current:  Lo0, Lo100, Lo200                                     │
│ Desired:  Lo100, Lo300                                          │
│                                                                  │
│ Analysis:                                                       │
│   • Lo0   → Not in intent, POLICY=safe → IGNORE                │
│   • Lo100 → In both → Check if different                        │
│             IP matches? Netmask matches? Description matches?   │
│             If different → UPDATE                               │
│             If same → SKIP (no change)                          │
│   • Lo200 → Not in intent, POLICY=safe → IGNORE                │
│   • Lo300 → Not on device → CREATE                             │
│                                                                  │
│ Changes Generated:                                              │
│   [Change(action="create", resource="loopback", id="300", ...)] │
│   (Lo100 unchanged, Lo0/Lo200 ignored)                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ apply_change(change)                                            │
│   • Build XML for Lo300                                         │
│   • POST to NSO: .../interface/Loopback                         │
│   • NSO applies via NETCONF                                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ RESULT:                                                         │
│   Lo0   → Still exists (ignored as intended)                    │
│   Lo100 → Still exists (matched intent)                         │
│   Lo200 → Still exists (ignored as intended)                    │
│   Lo300 → CREATED                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Compare with Strict Mode**:

```
┌─────────────────────────────────────────────────────────────────┐
│ SAME SCENARIO with delete_unmanaged_loopbacks = true           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ calculate_loopback_changes(device_intent)                       │
│                                                                  │
│ Current:  Lo0, Lo100, Lo200                                     │
│ Desired:  Lo100, Lo300                                          │
│                                                                  │
│ Analysis:                                                       │
│   • Lo0   → Not in intent, POLICY=strict → DELETE              │
│   • Lo100 → In both, matches → SKIP                            │
│   • Lo200 → Not in intent, POLICY=strict → DELETE              │
│   • Lo300 → Not on device → CREATE                             │
│                                                                  │
│ Changes Generated:                                              │
│   [Change(action="delete", resource="loopback", id="0", ...),   │
│    Change(action="delete", resource="loopback", id="200", ...), │
│    Change(action="create", resource="loopback", id="300", ...)] │
│                                                                  │
│ ⚠️  WARNING logged:                                             │
│   "delete_unmanaged_loopbacks=True: Will DELETE 2 loopbacks"   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ RESULT:                                                         │
│   Lo0   → DELETED                                               │
│   Lo100 → Still exists (matched intent)                         │
│   Lo200 → DELETED                                               │
│   Lo300 → CREATED                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Insight**: Safe mode preserves existing configs not in intent, strict mode enforces intent as single source of truth.

---

### Flow 3: Intent Merging Workflow

**When specifying multiple intent files, how they merge**

```
┌─────────────────────────────────────────────────────────────────┐
│ USER COMMAND:                                                   │
│ apply_device_intent.py                                          │
│   --intent intent/device_loopbacks.yaml                         │
│   --intent intent/device_bgp_configs.yaml                       │
│   --device dev-dist-rtr01                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ LOAD FILE 1: device_loopbacks.yaml                              │
│                                                                  │
│ devices:                                                        │
│   - name: dev-dist-rtr01                                        │
│     device_type: ios-xe                                         │
│     delete_unmanaged_loopbacks: false                           │
│     loopbacks:                                                  │
│       - id: 100                                                 │
│         ipv4: 10.100.100.1                                      │
│       - id: 200                                                 │
│         ipv4: 10.200.200.1                                      │
│     bgp: null  # No BGP in this file                            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ LOAD FILE 2: device_bgp_configs.yaml                            │
│                                                                  │
│ devices:                                                        │
│   - name: dev-dist-rtr01                                        │
│     device_type: ios-xe                                         │
│     delete_unmanaged_bgp_neighbors: false                       │
│     loopbacks: []  # No loopbacks in this file                  │
│     bgp:                                                        │
│       asn: 65001                                                │
│       router_id: 10.100.100.2                                   │
│       neighbors: [...]                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ MERGE PROCESS: merge_intents([intent1, intent2])                │
│                                                                  │
│ For device "dev-dist-rtr01":                                    │
│                                                                  │
│ 1. Merge Loopbacks:                                             │
│    • From file1: [Lo100, Lo200]                                 │
│    • From file2: [] (empty)                                     │
│    • Result: [Lo100, Lo200]                                     │
│                                                                  │
│    If both files had loopbacks:                                 │
│      • Combine lists                                            │
│      • If duplicate ID → last file wins                         │
│                                                                  │
│ 2. Merge BGP:                                                   │
│    • From file1: null                                           │
│    • From file2: {asn: 65001, ...}                              │
│    • Result: {asn: 65001, ...}                                  │
│                                                                  │
│    If both files had BGP:                                       │
│      • Last file wins (complete replacement)                    │
│                                                                  │
│ 3. Merge Deletion Flags:                                        │
│    • delete_unmanaged_loopbacks: file1=false, file2=false       │
│    • Result: false (last value)                                 │
│    • delete_unmanaged_bgp_neighbors: file1=false, file2=false   │
│    • Result: false (last value)                                 │
│                                                                  │
│ MERGED INTENT:                                                  │
│ devices:                                                        │
│   - name: dev-dist-rtr01                                        │
│     device_type: ios-xe                                         │
│     delete_unmanaged_loopbacks: false                           │
│     delete_unmanaged_bgp_neighbors: false                       │
│     loopbacks: [Lo100, Lo200]                                   │
│     bgp: {asn: 65001, router_id: ..., neighbors: [...]}        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ PROCEED WITH DEPLOYMENT using merged intent                     │
│   • Calculate changes for loopbacks                             │
│   • Calculate changes for BGP                                   │
│   • Apply all changes                                           │
└─────────────────────────────────────────────────────────────────┘
```

**Merge Rules Summary**:
- **Same device in multiple files**: Configs merged, not replaced
- **Loopbacks**: Combined list, duplicate IDs → last wins
- **BGP**: Last definition wins (complete replacement)
- **Deletion flags**: Last value wins
- **Different devices**: No merging needed, just combined

**Example - Duplicate Loopback IDs**:

```yaml
# File 1
loopbacks:
  - id: 100
    ipv4: 10.100.100.1  # Old IP
    description: "Old description"

# File 2
loopbacks:
  - id: 100
    ipv4: 10.100.100.99  # New IP
    description: "New description"

# Merged Result
loopbacks:
  - id: 100
    ipv4: 10.100.100.99  # File 2 wins
    description: "New description"
```

---

### Flow 4: Handling Unmanaged Resources

**What happens to resources NOT in intent**

```
┌─────────────────────────────────────────────────────────────────┐
│ DEVICE CURRENT STATE (before deployment)                        │
│                                                                  │
│ BGP:                                                            │
│   AS: 65001                                                     │
│   Router-ID: 10.100.100.1                                       │
│   Neighbors:                                                    │
│     • 10.200.200.1 (in intent) - iBGP to core-rtr01            │
│     • 192.168.1.1 (NOT in intent) - Manual config              │
│     • 192.168.2.1 (NOT in intent) - Manual config              │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ INTENT FILE                                                     │
│                                                                  │
│ devices:                                                        │
│   - name: dist-rtr01                                            │
│     delete_unmanaged_bgp_neighbors: ???                         │
│     bgp:                                                        │
│       asn: 65001                                                │
│       neighbors:                                                │
│         - ip: 10.200.200.1  # Only this one in intent          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│   SAFE MODE      │    │   STRICT MODE    │
│   (false)        │    │   (true)         │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ SAFE MODE BEHAVIOR                                              │
│                                                                  │
│ calculate_bgp_changes():                                        │
│   1. Check if BGP configured correctly                          │
│      → Yes, BGP AS and router-ID match                          │
│   2. Check if 10.200.200.1 exists                               │
│      → Yes, exists and matches                                  │
│   3. Find unmanaged neighbors:                                  │
│      current = {10.200.200.1, 192.168.1.1, 192.168.2.1}        │
│      desired = {10.200.200.1}                                   │
│      unmanaged = {192.168.1.1, 192.168.2.1}                     │
│   4. Check deletion policy → false (safe mode)                  │
│   5. Log: "Ignoring 2 unmanaged neighbors (safe mode)"         │
│   6. Return: [] (no changes)                                    │
│                                                                  │
│ RESULT:                                                         │
│   ✓ 10.200.200.1 → Preserved (in intent)                        │
│   ✓ 192.168.1.1  → Preserved (ignored by automation)            │
│   ✓ 192.168.2.1  → Preserved (ignored by automation)            │
│                                                                  │
│ OUTPUT: "✓ No changes needed - network is in desired state"     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STRICT MODE BEHAVIOR                                            │
│                                                                  │
│ calculate_bgp_changes():                                        │
│   1. Check if BGP configured correctly                          │
│      → Yes, but has extra neighbors                             │
│   2. Find unmanaged neighbors:                                  │
│      unmanaged = {192.168.1.1, 192.168.2.1}                     │
│   3. Check deletion policy → true (strict mode)                 │
│   4. ⚠️  WARNING: "Will DELETE 2 unmanaged neighbors"           │
│   5. Generate changes:                                          │
│      [Change(action="delete", resource="bgp-neighbor",          │
│              id="192.168.1.1", ...),                            │
│       Change(action="delete", resource="bgp-neighbor",          │
│              id="192.168.2.1", ...)]                            │
│                                                                  │
│ apply_changes():                                                │
│   • DELETE 192.168.1.1 via NSO API                              │
│   • DELETE 192.168.2.1 via NSO API                              │
│                                                                  │
│ RESULT:                                                         │
│   ✓ 10.200.200.1 → Preserved (in intent)                        │
│   ✗ 192.168.1.1  → DELETED (not in intent)                      │
│   ✗ 192.168.2.1  → DELETED (not in intent)                      │
│                                                                  │
│ OUTPUT: "Intent reconciliation complete: 2 succeeded"           │
└─────────────────────────────────────────────────────────────────┘
```

**Key Takeaway**: Safe mode is recommended for shared environments where manual configs may exist. Strict mode enforces infrastructure-as-code where automation is the ONLY source of truth.

**When to Use Each**:
- **Safe Mode (default)**: Production, shared environments, migration phase
- **Strict Mode**: Full automation, greenfield, dedicated dev environment

---

## Decision Trees

### Should I Use Device-Level or Service-Level?

```
┌─────────────────────────────────────────────────────────────────┐
│ START: Need to deploy configuration                             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │ Does each      │
            │ device need    │────YES────┐
            │ UNIQUE config? │           │
            └───────┬────────┘           │
                    │                    │
                   NO                    │
                    │                    │
                    ▼                    ▼
         ┌──────────────────┐   ┌──────────────────┐
         │ Same config      │   │ Each device has  │
         │ everywhere?      │   │ unique values?   │
         └─────────┬────────┘   └────────┬─────────┘
                   │                     │
                   ▼                     ▼
         ┌──────────────────┐   ┌──────────────────┐
         │ Use SERVICE-     │   │ Use DEVICE-      │
         │ LEVEL pattern    │   │ LEVEL pattern    │
         │                  │   │                  │
         │ Examples:        │   │ Examples:        │
         │ • L3VPN          │   │ • BGP            │
         │ • VRF            │   │ • Loopbacks      │
         │ • Multicast      │   │ • Interfaces     │
         │ • QoS policy     │   │ • Router-IDs     │
         └──────────────────┘   └──────────────────┘
```

**Detailed Examples**:

**Device-Level (BGP)**:
```yaml
# Each device MUST have unique router-ID
devices:
  - name: rtr01
    bgp:
      router_id: 10.1.1.1  # Unique!
      neighbors:
        - ip: 10.2.2.2     # Points to rtr02
  - name: rtr02
    bgp:
      router_id: 10.2.2.2  # Different!
      neighbors:
        - ip: 10.1.1.1     # Points to rtr01
```

**Service-Level (L3VPN - Future)**:
```yaml
# Same VRF on all devices
service_type: l3vpn
target_devices: [rtr01, rtr02, rtr03]
vrf_config:
  name: CUSTOMER_A      # Same everywhere
  rd: "65001:100"       # Same everywhere
  rt_import: "65001:100"
  rt_export: "65001:100"
```

---

### Safe Mode vs Strict Mode

```
┌─────────────────────────────────────────────────────────────────┐
│ START: Setting deletion policy                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │ Are you migrating     │
         │ from manual config    │─────YES────┐
         │ to automation?        │            │
         └──────────┬────────────┘            │
                    │                         │
                   NO                         │
                    │                         ▼
                    │              ┌──────────────────┐
                    │              │ Use SAFE MODE    │
                    │              │ (false)          │
                    │              │                  │
                    │              │ • Preserves      │
                    │              │   manual configs │
                    │              │ • Lower risk     │
                    │              │ • Recommended    │
                    │              │   for production │
                    │              └──────────────────┘
                    │
                    ▼
         ┌───────────────────────┐
         │ Do you control ALL    │
         │ config via automation │─────NO─────┐
         │ (no manual changes)?  │            │
         └──────────┬────────────┘            │
                    │                         │
                   YES                        │
                    │                         ▼
                    │              ┌──────────────────┐
                    │              │ Use SAFE MODE    │
                    │              │ (false)          │
                    │              │                  │
                    │              │ Manual configs   │
                    │              │ exist - don't    │
                    │              │ delete them!     │
                    │              └──────────────────┘
                    │
                    ▼
         ┌───────────────────────┐
         │ Is this a dedicated   │
         │ dev/test environment  │─────NO─────┐
         │ you can rebuild?      │            │
         └──────────┬────────────┘            │
                    │                         │
                   YES                        │
                    │                         ▼
                    │              ┌──────────────────┐
                    │              │ MAYBE strict     │
                    │              │                  │
                    │              │ Production =     │
                    │              │ be cautious!     │
                    │              └──────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │ Use STRICT MODE  │
         │ (true)           │
         │                  │
         │ • Enforces IaC   │
         │ • Higher risk    │
         │ • Full control   │
         │ • Dev/test only  │
         └──────────────────┘
```

**Risk Assessment**:

| Mode | Risk Level | Use Case | Impact of Mistake |
|------|-----------|----------|-------------------|
| Safe | Low | Production, shared env | Manual configs preserved |
| Strict | High | Dev, greenfield | Unintended deletions possible |

**Recommendation**: Start with safe mode, move to strict only after:
1. All configs migrated to intent files
2. No manual changes on devices
3. Full testing completed
4. Team trained on workflow

---

### When to Use --dry-run

```
┌─────────────────────────────────────────────────────────────────┐
│ START: About to run apply_device_intent.py                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │ Is this the FIRST     │
         │ time running this     │─────YES────┐
         │ specific command?     │            │
         └──────────┬────────────┘            │
                    │                         │
                   NO                         ▼
                    │              ┌──────────────────┐
                    │              │ ALWAYS use       │
                    │              │ --dry-run first! │
                    │              │                  │
                    │              │ Review output,   │
                    │              │ then run without │
                    │              │ --dry-run        │
                    │              └──────────────────┘
                    │
                    ▼
         ┌───────────────────────┐
         │ Did you modify the    │
         │ intent file since     │─────YES────┐
         │ last run?             │            │
         └──────────┬────────────┘            │
                    │                         │
                   NO                         ▼
                    │              ┌──────────────────┐
                    │              │ Use --dry-run    │
                    │              │                  │
                    │              │ Verify changes   │
                    │              │ are what you     │
                    │              │ expect           │
                    │              └──────────────────┘
                    │
                    ▼
         ┌───────────────────────┐
         │ Is this PRODUCTION    │
         │ environment?          │─────YES────┐
         └──────────┬────────────┘            │
                    │                         │
                   NO                         ▼
                    │              ┌──────────────────┐
                    │              │ ALWAYS use       │
                    │              │ --dry-run in     │
                    │              │ production!      │
                    │              │                  │
                    │              │ Get approval     │
                    │              │ before applying  │
                    │              └──────────────────┘
                    │
                    ▼
         ┌───────────────────────┐
         │ Are you confident     │
         │ in what will happen?  │─────NO─────┐
         └──────────┬────────────┘            │
                    │                         │
                   YES                        ▼
                    │              ┌──────────────────┐
                    │              │ Use --dry-run    │
                    │              │                  │
                    │              │ Better safe      │
                    │              │ than sorry!      │
                    │              └──────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │ OK to run        │
         │ without dry-run  │
         │                  │
         │ But dry-run      │
         │ never hurts!     │
         └──────────────────┘
```

**Best Practice**: Use `--dry-run` by default, only skip when:
- Exact same command run successfully minutes ago
- Dev environment you can easily rebuild
- Small, well-understood change

**Never skip dry-run when**:
- First time with new device
- Production environment
- Deletion policy enabled
- Multiple devices affected

---

## Common Scenarios

### Scenario 1: New Router Onboarding

**Situation**: Need to add brand new router to network with full config

**Timeline**: 15-30 minutes

**Steps**:

```bash
# === PHASE 1: Inventory Setup (5 min) ===

# 1. Add to NSO (assumes already done by network team)
# Verify device appears in NSO
python scripts/sync_devices.py

# 2. Add to inventory
vim inventory/hosts.yaml
```

```yaml
# Add new device
new-edge-rtr01:
  hostname: new-edge-rtr01
  ip_address: 10.10.20.191
  device_type: ios-xe
  protocol: ssh
  groups:
    - edge
    - router
    - production
    - bgp_enabled
  vars:
    loopback0_ip: 10.150.150.1
    bgp_router_id: 10.150.150.1
    bgp_as: 65001
    region: east
```

```bash
# 3. Validate inventory
python -c "
from nso_orchestration.automation.inventory_loader import load_inventory
inv = load_inventory()
device = inv.get_device('new-edge-rtr01')
print(f'✓ Device added: {device}')
print(f'  Type: {device.device_type}')
print(f'  Groups: {device.groups}')
print(f'  BGP AS: {device.get(\"bgp_as\")}')
"

# === PHASE 2: Intent Creation (5 min) ===

# 4. Create loopback intent
vim intent/device_loopbacks.yaml
```

```yaml
# Add to existing file
devices:
  # ... existing devices ...
  
  - name: new-edge-rtr01
    device_type: ios-xe
    delete_unmanaged_loopbacks: false  # Safe mode for new device
    loopbacks:
      - id: 0
        ipv4: 10.150.150.1
        netmask: 255.255.255.255
        description: "Management & BGP Router-ID"
      
      - id: 100
        ipv4: 10.151.151.1
        netmask: 255.255.255.255
        description: "Service loopback"
```

```bash
# 5. Create BGP intent
vim intent/device_bgp_configs.yaml
```

```yaml
# Add to existing file
devices:
  # ... existing devices ...
  
  - name: new-edge-rtr01
    device_type: ios-xe
    delete_unmanaged_bgp_neighbors: false  # Safe mode
    bgp:
      asn: 65001
      router_id: 10.150.150.1
      neighbors:
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01"
          update_source: "Loopback0"
        
        - ip: 10.200.200.2
          remote_asn: 65001
          description: "iBGP to dev-core-rtr01"
          update_source: "Loopback0"
```

```bash
# === PHASE 3: Validation (2 min) ===

# 6. Validate intent files
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device new-edge-rtr01 \
  --dry-run

# Review output:
# Expected: "Planned changes: 3 total"
#   - 3 creates: Lo0, Lo100, BGP

# === PHASE 4: Deployment (5 min) ===

# 7. Deploy loopbacks first
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --device new-edge-rtr01

# Expected: "✓ Intent reconciliation complete: 2 succeeded"

# 8. Deploy BGP
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device new-edge-rtr01

# Expected: "✓ Intent reconciliation complete: 1 succeeded"

# === PHASE 5: Verification (5 min) ===

# 9. Verify idempotency (no changes on second run)
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device new-edge-rtr01

# Expected: "✓ No changes needed - network is in desired state"

# 10. Verify on device (manual check)
# SSH to device and verify:
# - show ip interface brief | include Loopback
# - show ip bgp summary
# - show ip bgp neighbors
```

**Success Criteria**:
- ✅ Device in inventory with correct vars
- ✅ Intent files validated
- ✅ All configs deployed successfully
- ✅ Idempotency verified
- ✅ BGP neighbors in "Established" state

**Common Issues**:
- **Device not synced**: Run `sync_devices.py` first
- **Template not found**: Check device_type matches (ios-xe vs ios-xr)
- **BGP neighbors down**: Check reachability, loopback configs on peer devices

---

### Scenario 2: BGP Neighbor Addition

**Situation**: Add new BGP peering to existing router (e.g., new ISP connection)

**Timeline**: 5-10 minutes

**Steps**:

```bash
# === PHASE 1: Current State (1 min) ===

# 1. Check current BGP config
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run

# Expected: "✓ No changes needed" (idempotent)

# === PHASE 2: Modify Intent (2 min) ===

# 2. Edit BGP intent
vim intent/device_bgp_configs.yaml
```

```yaml
# Find dist-rtr01, add new neighbor
devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_bgp_neighbors: false
    bgp:
      asn: 65001
      router_id: 10.100.100.1
      neighbors:
        # Existing neighbor
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01"
          update_source: "Loopback0"
        
        # NEW NEIGHBOR - External ISP
        - ip: 203.0.113.1
          remote_asn: 65500
          description: "eBGP to ISP-A"
          # No update_source for eBGP (uses physical interface)
```

```bash
# === PHASE 3: Preview & Deploy (3 min) ===

# 3. Preview changes
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run

# Expected: "Planned changes: 1 total"
#   - UPDATE bgp (adds new neighbor, preserves existing)

# 4. Apply changes
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# Expected: "✓ Intent reconciliation complete: 1 succeeded"

# === PHASE 4: Verification (2 min) ===

# 5. Verify idempotency
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# Expected: "✓ No changes needed"

# 6. Check BGP session on device
# show ip bgp summary
# show ip bgp neighbors 203.0.113.1
```

**What Happened Internally**:
1. Framework detected BGP already configured
2. Compared current neighbors vs intent
3. Found new neighbor not on device
4. Re-rendered complete BGP config with both neighbors
5. Applied via NSO (atomic update)
6. Existing neighbor unaffected (no session flap)

**Success Criteria**:
- ✅ New neighbor added
- ✅ Existing neighbor unchanged (check uptime - should not reset)
- ✅ New BGP session established
- ✅ Idempotency verified

---

### Scenario 3: Migrating from Manual to Automation

**Situation**: Existing network with manual configs, want to bring under automation control

**Timeline**: 30-60 minutes per device

**Approach**: Safe migration with phased onboarding

**Steps**:

```bash
# === PHASE 1: Discovery (10 min) ===

# 1. Sync device to get current config
python scripts/sync_devices.py

# 2. Query current config (manual inspection)
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('10.10.20.49')
config = client.get_device_config('dist-rtr01')

# Check loopbacks
loopbacks = config.get('tailf-ncs:config', {}).get('tailf-ned-cisco-ios:interface', {}).get('Loopback', [])
print('Current Loopbacks:')
for lb in loopbacks:
    print(f\"  - Lo{lb.get('name')}: {lb.get('ip', {}).get('address', {}).get('primary', {})}\")

# Check BGP
bgp = config.get('tailf-ncs:config', {}).get('tailf-ned-cisco-ios:router', {}).get('bgp', {})
print(f\"\\nCurrent BGP AS: {bgp.get('as-no')}\")
neighbors = bgp.get('neighbor', [])
if not isinstance(neighbors, list):
    neighbors = [neighbors]
print('Current BGP Neighbors:')
for n in neighbors:
    print(f\"  - {n.get('id')} (AS {n.get('remote-as')})\")
"

# 3. Document all MANUAL configs (important!)
# Create a backup/documentation file
vim docs/dist-rtr01_manual_configs.txt
```

```text
# Manual Configs on dist-rtr01 (before automation)

Loopbacks:
- Lo0: 10.100.100.1/32 (Management - DO NOT TOUCH)
- Lo99: 192.168.99.1/32 (Monitoring - DO NOT TOUCH)
- Lo100: 10.100.100.1/32 (OK to manage)

BGP Neighbors:
- 10.200.200.1 (iBGP to core - OK to manage)
- 192.168.50.1 (Test neighbor - DO NOT TOUCH for now)

SNMP, ACLs, etc:
- Multiple manual configs exist - document separately
```

```bash
# === PHASE 2: Create Intent (SAFE MODE) (10 min) ===

# 4. Create intent with SAFE MODE enabled
vim intent/device_loopbacks.yaml
```

```yaml
# Add device with safe mode
devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_loopbacks: false  # CRITICAL: Safe mode!
    loopbacks:
      # Only manage specific loopbacks we want automated
      - id: 100
        ipv4: 10.100.100.1
        netmask: 255.255.255.255
        description: "Management loopback - AUTOMATED"
      
      # Explicitly NOT including:
      # - Lo0 (leave as manual)
      # - Lo99 (leave as manual)
```

```yaml
# BGP with safe mode
devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_bgp_neighbors: false  # CRITICAL: Safe mode!
    bgp:
      asn: 65001
      router_id: 10.100.100.1
      neighbors:
        # Only manage production neighbor
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01 - AUTOMATED"
        
        # Explicitly NOT including:
        # - 192.168.50.1 (test neighbor - leave as manual for now)
```

```bash
# === PHASE 3: Test in Dev First (10 min) ===

# 5. Test on dev device first (if available)
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --device dev-dist-rtr01 \  # Dev device!
  --dry-run

# 6. Deploy to dev
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --device dev-dist-rtr01

# 7. Verify dev device unaffected
# Check that manual configs still exist

# === PHASE 4: Production Migration (10 min) ===

# 8. Dry-run on production device
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run \
  --verbose

# 9. Review output CAREFULLY
# Should see:
# - "delete_unmanaged_loopbacks=False (safe mode)"
# - "Ignoring X unmanaged loopbacks: [0, 99]"
# - "delete_unmanaged_bgp_neighbors=False (safe mode)"
# - "Ignoring 1 unmanaged BGP neighbors: [192.168.50.1]"

# 10. If output looks good, deploy
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# === PHASE 5: Verification (10 min) ===

# 11. Verify managed configs deployed
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01

# Expected: "✓ No changes needed"

# 12. Verify manual configs STILL EXIST
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('10.10.20.49')
client.sync_from_device('dist-rtr01')
config = client.get_device_config('dist-rtr01')

loopbacks = config.get('tailf-ncs:config', {}).get('tailf-ned-cisco-ios:interface', {}).get('Loopback', [])
lb_ids = [lb.get('name') for lb in loopbacks]

print('Loopbacks after migration:')
print(f'  Found: {lb_ids}')
print(f'  Lo0 preserved: {\"0\" in lb_ids}')
print(f'  Lo99 preserved: {\"99\" in lb_ids}')
print(f'  Lo100 managed: {\"100\" in lb_ids}')
"

# === PHASE 6: Gradual Expansion (ongoing) ===

# 13. Over time, gradually add more resources to intent
# Add one loopback at a time, verify each time

# 14. Eventually, when ALL configs in intent, can enable strict mode
# But only after careful planning!
```

**Success Criteria**:
- ✅ Managed configs deployed correctly
- ✅ Manual configs preserved (not deleted)
- ✅ No service disruption
- ✅ Idempotency verified
- ✅ Team comfortable with workflow

**Migration Timeline**:
- **Week 1**: Test on dev devices
- **Week 2**: Migrate 1-2 pilot production devices
- **Week 3**: Migrate remaining devices in batches
- **Week 4+**: Gradually expand managed resources

**Common Pitfalls**:
- ❌ Forgetting to set safe mode (delete_unmanaged = false)
- ❌ Not documenting manual configs before migration
- ❌ Migrating all devices at once (do in batches!)
- ❌ Enabling strict mode too early

---

### Scenario 4: Removing a Device

**Situation**: Decommissioning a router, need to clean up configs

**Timeline**: 10-15 minutes

**Steps**:

```bash
# === PHASE 1: Remove from Intent (2 min) ===

# 1. Remove device from loopback intent
vim intent/device_loopbacks.yaml
```

```yaml
devices:
  # ... keep other devices ...
  
  # REMOVE or comment out decommissioned device
  # - name: old-rtr01
  #   device_type: ios-xe
  #   loopbacks: [...]
```

```bash
# 2. Remove from BGP intent
vim intent/device_bgp_configs.yaml
```

```yaml
devices:
  # ... keep other devices ...
  
  # REMOVE or comment out
  # - name: old-rtr01
  #   bgp: ...
```

```bash
# === PHASE 2: Remove BGP Peers Pointing to This Device (5 min) ===

# 3. Find devices that peer with old-rtr01
grep -r "10.180.180.1" intent/  # old-rtr01's loopback

# 4. Remove neighbor entries from peer devices
vim intent/device_bgp_configs.yaml
```

```yaml
# Example: core-rtr01 had neighbor to old-rtr01
devices:
  - name: core-rtr01
    bgp:
      neighbors:
        # REMOVE this neighbor
        # - ip: 10.180.180.1
        #   remote_asn: 65001
        #   description: "iBGP to old-rtr01"
        
        # Keep other neighbors
        - ip: 10.100.100.1
          remote_asn: 65001
          description: "iBGP to dist-rtr01"
```

```bash
# === PHASE 3: Deploy Neighbor Removal (3 min) ===

# 5. Deploy updated configs to peer devices
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device core-rtr01 \
  --dry-run

# Expected: "1 update: BGP neighbor removed"

python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device core-rtr01

# === PHASE 4: Remove from Inventory (2 min) ===

# 6. Remove from inventory
vim inventory/hosts.yaml
```

```yaml
devices:
  # ... keep other devices ...
  
  # REMOVE decommissioned device
  # old-rtr01:
  #   hostname: old-rtr01
  #   ip_address: 10.10.20.199
  #   ...
```

```bash
# 7. Validate inventory
python -c "
from nso_orchestration.automation.inventory_loader import load_inventory
inv = load_inventory()
is_valid, issues = inv.validate()
print('✓ Valid' if is_valid else f'Issues: {issues}')
print(f'Device count: {len(inv.list_devices())}')
"

# === PHASE 5: Optional - Remove from NSO (manual) ===

# 8. If device no longer exists physically, remove from NSO
# (This is typically done via NSO CLI or GUI, not via this framework)

# NSO CLI:
# devices device old-rtr01
# no devices device old-rtr01
# commit
```

**Success Criteria**:
- ✅ Device removed from all intent files
- ✅ BGP neighbors to device removed from peers
- ✅ Device removed from inventory
- ✅ Peer devices updated successfully
- ✅ No errors in deployment

**Important Notes**:
- Remove device from intent files BEFORE inventory (so you can still deploy final cleanup)
- Remove BGP neighbors from peers BEFORE removing the device itself
- Keep backups of intent files before major deletions

---

## Troubleshooting Guide

### NSO Connection Issues

**Symptom**: `NSO health check failed`, connection timeout, or authentication errors

**Diagnosis**:

```bash
# 1. Check NSO is reachable
ping $NSO_HOST

# 2. Check NSO port is open
nc -zv $NSO_HOST 8080

# 3. Verify credentials
curl -u $NSO_USER:$NSO_PW http://$NSO_HOST:8080/restconf/data/tailf-ncs:devices

# 4. Check environment variables
echo "NSO_HOST=$NSO_HOST"
echo "NSO_PORT=$NSO_PORT"
echo "NSO_USER=$NSO_USER"
echo "NSO_PW=***"

# 5. Test with Python
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient(host='$NSO_HOST', port=8080, username='$NSO_USER', password='$NSO_PW')
if client.health_check():
    print('✓ NSO connection successful')
else:
    print('✗ NSO connection failed')
"
```

**Common Causes & Solutions**:

| Cause | Solution |
|-------|----------|
| VPN not connected | Connect to Cisco DevNet VPN |
| Wrong host/port | Check NSO_HOST and NSO_PORT environment variables |
| Wrong credentials | Verify NSO_USER and NSO_PW (default: developer/C1sco12345) |
| NSO not running | Start NSO service (if local) or contact admin |
| Firewall blocking | Check firewall rules, security groups |
| SSL/TLS issues | Set `verify_ssl=False` for sandbox environments |

**Quick Fix**:

```bash
# Reset environment variables
export NSO_HOST=10.10.20.49
export NSO_PORT=8080
export NSO_USER=developer
export NSO_PW=C1sco12345

# Test immediately
python scripts/sync_devices.py
```

---

### Validation Errors

**Symptom**: `ValidationError` when loading intent files

**Example Errors**:

**Error 1: Invalid IP Address**

```
ValidationError: Invalid IPv4 address: 10.100.100.256
  Octets must be 0-255
```

**Fix**:
```yaml
# WRONG
ipv4: 10.100.100.256

# CORRECT
ipv4: 10.100.100.1
```

**Error 2: Invalid Netmask**

```
ValidationError: Invalid subnet mask: 255.255.255.256
  Must be a valid dotted-decimal mask
```

**Fix**:
```yaml
# WRONG
netmask: 255.255.255.256

# CORRECT
netmask: 255.255.255.255
```

**Error 3: Invalid BGP AS Number**

```
ValidationError: ensure this value is less than or equal to 4294967295
```

**Fix**:
```yaml
# WRONG
asn: 9999999999  # Too large!

# CORRECT
asn: 65001  # Valid AS number
```

**Error 4: Duplicate Device Names**

```
ValidationError: Duplicate device names found: {'dist-rtr01'}
```

**Fix**:
```yaml
# WRONG - same device twice
devices:
  - name: dist-rtr01
    loopbacks: [...]
  - name: dist-rtr01  # Duplicate!
    bgp: ...

# CORRECT - one device per name
devices:
  - name: dist-rtr01
    loopbacks: [...]
    bgp: ...
```

**Error 5: Duplicate BGP Neighbor IPs**

```
ValidationError: Duplicate neighbor IPs: {'10.0.0.1'}
```

**Fix**:
```yaml
# WRONG
neighbors:
  - ip: 10.0.0.1
    remote_asn: 65001
  - ip: 10.0.0.1  # Duplicate!
    remote_asn: 65002

# CORRECT
neighbors:
  - ip: 10.0.0.1
    remote_asn: 65001
  - ip: 10.0.0.2  # Different IP
    remote_asn: 65002
```

**Debugging Process**:

```bash
# 1. Try to load and validate
python -c "
from nso_orchestration.automation.device_models import NetworkIntent
import yaml

with open('intent/device_bgp_configs.yaml') as f:
    data = yaml.safe_load(f)

try:
    intent = NetworkIntent(**data)
    print('✓ Validation passed')
except Exception as e:
    print(f'✗ Validation failed: {e}')
"

# 2. Use --verbose for detailed errors
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --verbose

# 3. Check YAML syntax
python -c "
import yaml
with open('intent/device_bgp_configs.yaml') as f:
    data = yaml.safe_load(f)
    print('✓ YAML syntax valid')
"
```

---

### Deployment Failures

**Symptom**: `✗ Failed to apply: [device]`, deployment errors, or partial success

**Diagnosis Steps**:

```bash
# 1. Check verbose output
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --verbose

# 2. Verify device is synced
python scripts/sync_devices.py

# 3. Check device reachability from NSO
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('$NSO_HOST')
devices = client.get_devices()
print(f'Devices in NSO: {devices}')
"

# 4. Try manual NSO operation
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('$NSO_HOST')
config = client.get_device_config('dist-rtr01')
print('Device config retrieved' if config else 'Failed to get config')
"
```

**Common Failures**:

**Failure 1: Device Not Synced**

```
Error: Could not retrieve config from dist-rtr01
```

**Solution**:
```bash
python scripts/sync_devices.py
# Then retry deployment
```

**Failure 2: Template Not Found**

```
Error: Template not found: ios-xr/bgp_service.xml.j2
```

**Solution**:
```bash
# Check template exists
ls -la nso_orchestration/templates/ios-xr/

# Check device type in inventory
python -c "
from nso_orchestration.automation.inventory_loader import load_inventory
inv = load_inventory()
device = inv.get_device('dist-rtr01')
print(f'Device type: {device.device_type}')
"

# Fix device_type if wrong (should be ios-xe or ios-xr)
vim inventory/hosts.yaml
```

**Failure 3: NSO Validation Error**

```
Error: HTTP error on POST: 400 - Invalid configuration
```

**Solution**:
```bash
# 1. Check the XML that was sent
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --dry-run

# This saves to artifacts/dist-rtr01_bgp_service.xml

# 2. Inspect the XML
cat artifacts/dist-rtr01_bgp_service.xml

# 3. Common issues:
# - Invalid XML syntax
# - Wrong NED namespace
# - Missing required fields
# - Invalid values (AS number, IP address)

# 4. Fix template if needed
vim nso_orchestration/templates/ios-xe/bgp_service.xml.j2
```

**Failure 4: Partial Deployment**

```
Intent reconciliation complete: 2 succeeded, 1 failed
```

**Solution**:
```bash
# 1. Identify which change failed (check logs)
# Look for "✗ Failed to apply: [device]"

# 2. Fix the issue for failed device

# 3. Re-run (idempotency means successful devices won't be changed)
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml

# Only the failed device will be retried
```

**Failure 5: Rollback Needed**

```
Deployment failed - need to rollback
```

**Solution**:
```bash
# 1. Check rollback files
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('$NSO_HOST')
rollbacks = client.get_rollback_files()
if rollbacks:
    print('Available rollbacks:')
    for rb in rollbacks:
        print(f'  - {rb}')
else:
    print('No rollback files')
"

# 2. Rollback to most recent (ID 0)
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('$NSO_HOST')
if client.rollback(0):
    print('✓ Rollback successful')
else:
    print('✗ Rollback failed')
"

# 3. Verify rollback
python scripts/sync_devices.py
```

---

### Idempotency Issues

**Symptom**: Framework keeps trying to apply same change on every run

**Example**:

```bash
# First run
python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml
# Output: "1 succeeded"

# Second run (should show no changes, but doesn't)
python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml
# Output: "1 succeeded" (WRONG - should be "No changes needed")
```

**Diagnosis**:

```bash
# 1. Enable verbose logging
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-rtr01 \
  --verbose

# Look for:
# - "BGP already configured correctly" (should appear on 2nd run)
# - "Planned changes: X" (should be 0 on 2nd run)

# 2. Manually check idempotency
python -c "
from nso_orchestration.automation.nso_client import NSOClient
from nso_orchestration.automation.device_models import NetworkIntent
from nso_orchestration.services.bgp_peering import check_bgp_configured
from nso_orchestration.automation.service_models import BGPPeeringServiceIntent, BGPNeighborIntent
import yaml

# Load intent
with open('intent/device_bgp_configs.yaml') as f:
    intent_data = yaml.safe_load(f)

intent = NetworkIntent(**intent_data)
device_intent = intent.get_device('dist-rtr01')

# Convert to service format
service_intent = BGPPeeringServiceIntent(
    local_as=device_intent.bgp.asn,
    router_id=device_intent.bgp.router_id,
    neighbors=[
        BGPNeighborIntent(
            neighbor_ip=n.ip,
            remote_as=n.remote_asn,
            description=n.description,
            update_source=n.update_source
        )
        for n in device_intent.bgp.neighbors
    ]
)

# Check
client = NSOClient('10.10.20.49')
is_configured = check_bgp_configured(client, 'dist-rtr01', service_intent)
print(f'BGP configured correctly: {is_configured}')
"
```

**Common Causes**:

**Cause 1: Field Name Mismatch**

```python
# Intent has:
ip: "10.0.0.1"
remote_asn: 65001

# Check is looking for:
neighbor_ip: "10.0.0.1"  # Different field name!
remote_as: 65001         # Different field name!
```

**Solution**: Already fixed in codebase (device_engine.py converts formats)

**Cause 2: NSO Data Structure Changes**

```python
# BGP returned as list, but code expects dict
bgp_config = config['router']['bgp']  # Could be list or dict!

# Solution: Always handle as list
if not isinstance(bgp_config, list):
    bgp_config = [bgp_config]
```

**Solution**: Already fixed in codebase

**Cause 3: Router-ID Nested Incorrectly**

```python
# Router-ID is nested: bgp.bgp.router-id (not bgp.router-id)
current_router_id = bgp_process.get('router-id')  # WRONG

# Correct:
bgp_sub = bgp_process.get('bgp', {})
current_router_id = bgp_sub.get('router-id')  # CORRECT
```

**Solution**: Already fixed in codebase

**Cause 4: Device Not Synced**

```
Device has latest config, but NSO CDB is stale
```

**Solution**:
```bash
# Always sync before checking
python scripts/sync_devices.py

# Or enable auto-sync in code (already done in device_engine.py)
```

**Verification**:

```bash
# Proper idempotency test:
# 1. Deploy
python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml --device dist-rtr01

# 2. Immediately run again (should show no changes)
python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml --device dist-rtr01
# Expected: "✓ No changes needed - network is in desired state"

# 3. If still showing changes, investigate with verbose flag
python scripts/apply_device_intent.py --intent intent/device_bgp_configs.yaml --device dist-rtr01 --verbose
```

---

## Development Workflows

### Adding a New Resource Type

**Example**: Adding OSPF support

**Timeline**: 2-4 hours for basic implementation

**Steps**:

```bash
# === STEP 1: Create Pydantic Models (30 min) ===

vim nso_orchestration/automation/device_models.py
```

```python
# Add to device_models.py

class OSPFNetworkIntent(BaseModel):
    """Intent for OSPF network statement."""
    
    network: str = Field(..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    wildcard: str = Field(...)
    area: int = Field(..., ge=0, le=4294967295)
    
    @field_validator("wildcard")
    @classmethod
    def validate_wildcard(cls, v: str) -> str:
        # Validate wildcard mask format
        octets = v.split(".")
        for octet in octets:
            num = int(octet)
            if not 0 <= num <= 255:
                raise ValueError(f"Invalid wildcard mask: {v}")
        return v


class OSPFIntent(BaseModel):
    """Intent for OSPF configuration."""
    
    process_id: int = Field(..., ge=1, le=65535)
    router_id: str | None = Field(None)
    networks: list[OSPFNetworkIntent] = Field(default_factory=list)
    passive_interfaces: list[str] = Field(default_factory=list)


# Add to DeviceIntent
class DeviceIntent(BaseModel):
    name: str
    device_type: Literal["ios", "ios-xe", "ios-xr", "nxos"]
    loopbacks: list[LoopbackIntent] = Field(default_factory=list)
    bgp: BGPIntent | None = None
    ospf: OSPFIntent | None = None  # NEW
    
    delete_unmanaged_loopbacks: bool = False
    delete_unmanaged_bgp_neighbors: bool = False
    delete_unmanaged_ospf_networks: bool = False  # NEW
```

```bash
# === STEP 2: Create Service Function (1 hour) ===

vim nso_orchestration/services/ospf.py
```

```python
"""
OSPF service deployment module.
"""

from loguru import logger
from pathlib import Path

from nso_orchestration.automation.nso_client import NSOClient
from nso_orchestration.automation.template_renderer import render_template


def check_ospf_configured(client: NSOClient, device_name: str, intent) -> bool:
    """Check if OSPF is already configured according to intent."""
    logger.info(f"[{device_name}] Checking if OSPF already configured")
    
    try:
        client.sync_from_device(device_name)
        config = client.get_device_config(device_name)
        
        if not config:
            return False
        
        # Navigate to OSPF config
        ospf_config = (
            config.get("tailf-ncs:config", {})
            .get("tailf-ned-cisco-ios:router", {})
            .get("ospf", [])
        )
        
        if not ospf_config:
            return False
        
        # Handle as list
        if not isinstance(ospf_config, list):
            ospf_config = [ospf_config]
        
        # Find process matching our ID
        ospf_process = None
        for process in ospf_config:
            if str(process.get("id")) == str(intent.process_id):
                ospf_process = process
                break
        
        if not ospf_process:
            return False
        
        # Check router-ID (if specified)
        if intent.router_id:
            current_router_id = ospf_process.get("router-id")
            if current_router_id != intent.router_id:
                return False
        
        # Check networks (basic check - could be more thorough)
        current_networks = ospf_process.get("network", [])
        if not isinstance(current_networks, list):
            current_networks = [current_networks] if current_networks else []
        
        if len(current_networks) != len(intent.networks):
            return False
        
        logger.info(f"[{device_name}] ✓ OSPF already configured correctly")
        return True
        
    except Exception as e:
        logger.error(f"[{device_name}] Error checking OSPF config: {e}")
        return False


def deploy_ospf_service(
    client: NSOClient,
    device_name: str,
    intent,
    dry_run: bool = False,
    inventory=None
) -> tuple[bool, str]:
    """Deploy OSPF service to a device."""
    
    if inventory is None:
        from nso_orchestration.automation.inventory_loader import load_inventory
        inventory = load_inventory()
    
    device = inventory.get_device(device_name)
    
    logger.info(f"[{device_name}] Deploying OSPF service")
    
    # Idempotency check
    if not dry_run:
        if check_ospf_configured(client, device_name, intent):
            return True, "Already configured (no changes needed)"
    
    # Select template
    if device and device.device_type == "ios-xr":
        template_name = "ios-xr/ospf_service.xml.j2"
    else:
        template_name = "ios-xe/ospf_service.xml.j2"
    
    # Render template
    try:
        config_xml = render_template(
            template_name,
            process_id=intent.process_id,
            router_id=intent.router_id,
            networks=[n.model_dump() for n in intent.networks],
            passive_interfaces=intent.passive_interfaces
        )
    except Exception as e:
        logger.error(f"[{device_name}] Template rendering failed: {e}")
        return False, f"Template rendering failed: {e}"
    
    # Dry-run
    if dry_run:
        artifact_dir = Path("artifacts")
        artifact_dir.mkdir(exist_ok=True)
        artifact_file = artifact_dir / f"{device_name}_ospf_service.xml"
        artifact_file.write_text(config_xml, encoding="utf-8")
        return True, f"DRY-RUN: Saved to {artifact_file}"
    
    # Apply configuration
    try:
        if device and device.device_type == "ios-xr":
            url = f"{client.base_url}/data/.../router/ospf"
        else:
            url = f"{client.base_url}/data/.../router"
        
        resp = client._safe_post(url, config_xml, content_type="application/yang-data+xml")
        
        if resp and resp.status_code in (200, 201, 204):
            return True, "OSPF service deployed successfully"
        else:
            return False, "OSPF deployment failed"
            
    except Exception as e:
        logger.error(f"[{device_name}] Exception during OSPF deployment: {e}")
        return False, f"Exception: {e}"


def remove_ospf_service(
    client: NSOClient,
    device_name: str,
    process_id: int,
    dry_run: bool = False
) -> tuple[bool, str]:
    """Remove OSPF service from a device."""
    
    if dry_run:
        return True, f"DRY-RUN: Would remove OSPF process {process_id}"
    
    try:
        url = f"{client.base_url}/data/.../router/ospf={process_id}"
        resp = client._safe_delete(url)
        
        if resp and resp.status_code in (200, 204):
            return True, "OSPF service removed successfully"
        else:
            return False, "OSPF removal failed"
            
    except Exception as e:
        return False, f"Exception: {e}"
```

```bash
# === STEP 3: Create Templates (30 min) ===

vim nso_orchestration/templates/ios-xe/ospf_service.xml.j2
```

```xml
<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <router xmlns="urn:ios">
    <ospf>
      <id>{{ process_id }}</id>
      {% if router_id %}
      <router-id>{{ router_id }}</router-id>
      {% endif %}
      {% for network in networks %}
      <network>
        <ip>{{ network.network }}</ip>
        <wildcard>{{ network.wildcard }}</wildcard>
        <area>{{ network.area }}</area>
      </network>
      {% endfor %}
      {% for interface in passive_interfaces %}
      <passive-interface>
        <name>{{ interface }}</name>
      </passive-interface>
      {% endfor %}
    </ospf>
  </router>
</config>
```

```bash
# === STEP 4: Add to Device Engine (30 min) ===

vim nso_orchestration/automation/device_engine.py
```

```python
# Add import
from nso_orchestration.services.ospf import (
    check_ospf_configured,
    deploy_ospf_service,
    remove_ospf_service,
)

# Add method to DeviceEngine class
def calculate_ospf_changes(self, device_intent: DeviceIntent) -> list[Change]:
    """Calculate changes needed to achieve desired OSPF state."""
    changes = []
    device_name = device_intent.name
    
    if not device_intent.ospf:
        logger.debug(f"[{device_name}] No OSPF intent specified")
        return changes
    
    ospf_intent = device_intent.ospf
    
    # Check if OSPF configured correctly
    is_configured = check_ospf_configured(self.client, device_name, ospf_intent)
    
    if not is_configured:
        changes.append(
            Change(
                action="create",
                device=device_name,
                resource_type="ospf",
                resource_id=str(ospf_intent.process_id),
                current=None,
                desired={
                    "process_id": ospf_intent.process_id,
                    "router_id": ospf_intent.router_id,
                    "networks": [n.model_dump() for n in ospf_intent.networks],
                },
            )
        )
    
    return changes

# Update calculate_changes to include OSPF
def calculate_changes(self, intent: NetworkIntent) -> list[Change]:
    all_changes = []
    
    for device_intent in intent.devices:
        logger.info(f"Calculating changes for {device_intent.name}")
        
        # Loopbacks
        loopback_changes = self.calculate_loopback_changes(device_intent)
        all_changes.extend(loopback_changes)
        
        # BGP
        bgp_changes = self.calculate_bgp_changes(device_intent)
        all_changes.extend(bgp_changes)
        
        # OSPF (NEW)
        ospf_changes = self.calculate_ospf_changes(device_intent)
        all_changes.extend(ospf_changes)
    
    return all_changes

# Update apply_change to handle OSPF
def apply_change(self, change: Change, dry_run: bool = False) -> bool:
    # ... existing loopback and BGP code ...
    
    elif change.resource_type == "ospf":
        if change.action in ("create", "update"):
            from nso_orchestration.automation.device_models import OSPFIntent, OSPFNetworkIntent
            
            # Reconstruct OSPF intent
            ospf_intent = OSPFIntent(
                process_id=change.desired["process_id"],
                router_id=change.desired.get("router_id"),
                networks=[
                    OSPFNetworkIntent(**n)
                    for n in change.desired["networks"]
                ]
            )
            
            success, message = deploy_ospf_service(
                self.client,
                change.device,
                ospf_intent,
                dry_run=dry_run,
                inventory=self.inventory
            )
            return success
        
        elif change.action == "delete":
            success, message = remove_ospf_service(
                self.client,
                change.device,
                int(change.resource_id),
                dry_run=dry_run
            )
            return success
```

```bash
# === STEP 5: Create Intent File (15 min) ===

vim intent/device_ospf_configs.yaml
```

```yaml
# OSPF Configuration Intent

devices:
  - name: dist-rtr01
    device_type: ios-xe
    delete_unmanaged_ospf_networks: false
    ospf:
      process_id: 1
      router_id: 10.100.100.1
      networks:
        - network: 10.100.100.0
          wildcard: 0.0.0.255
          area: 0
        
        - network: 192.168.1.0
          wildcard: 0.0.0.255
          area: 1
      
      passive_interfaces:
        - Loopback0
        - Loopback100
```

```bash
# === STEP 6: Test (1 hour) ===

# 1. Unit tests
vim tests/test_device_ospf.py
```

```python
import pytest
from nso_orchestration.automation.device_models import OSPFIntent, OSPFNetworkIntent

def test_ospf_intent_validation():
    """Test OSPF intent validates correctly."""
    intent = OSPFIntent(
        process_id=1,
        router_id="10.100.100.1",
        networks=[
            OSPFNetworkIntent(
                network="10.0.0.0",
                wildcard="0.0.0.255",
                area=0
            )
        ]
    )
    
    assert intent.process_id == 1
    assert intent.router_id == "10.100.100.1"
    assert len(intent.networks) == 1

def test_ospf_invalid_process_id():
    """Test invalid process ID rejected."""
    with pytest.raises(ValueError):
        OSPFIntent(process_id=99999, networks=[])

@pytest.mark.nso
def test_deploy_ospf(nso_client, test_device):
    """Test OSPF deployment."""
    from nso_orchestration.services.ospf import deploy_ospf_service
    
    intent = OSPFIntent(
        process_id=99,
        router_id="10.99.99.99",
        networks=[
            OSPFNetworkIntent(
                network="192.168.99.0",
                wildcard="0.0.0.255",
                area=0
            )
        ]
    )
    
    # Deploy
    success, message = deploy_ospf_service(nso_client, test_device, intent)
    assert success, message
    
    # Verify idempotency
    success2, message2 = deploy_ospf_service(nso_client, test_device, intent)
    assert success2
    assert "Already configured" in message2
    
    # Cleanup
    remove_ospf_service(nso_client, test_device, 99)
```

```bash
# 2. Run tests
pytest tests/test_device_ospf.py -v

# 3. Manual test
python scripts/apply_device_intent.py \
  --intent intent/device_ospf_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run

# 4. Deploy
python scripts/apply_device_intent.py \
  --intent intent/device_ospf_configs.yaml \
  --device dev-dist-rtr01

# 5. Verify idempotency
python scripts/apply_device_intent.py \
  --intent intent/device_ospf_configs.yaml \
  --device dev-dist-rtr01
# Expected: "✓ No changes needed"
```

**Checklist**:
- ✅ Pydantic models created and validated
- ✅ Service functions implemented (deploy, check, remove)
- ✅ Templates created for IOS-XE and IOS-XR
- ✅ Device engine updated
- ✅ Intent file created
- ✅ Unit tests written and passing
- ✅ Integration tests passing
- ✅ Manual testing successful
- ✅ Idempotency verified
- ✅ Documentation updated

---

### Adding Support for New Device Type

**Example**: Adding NX-OS support

**Timeline**: 1-2 hours for basic support

**Steps**:

```bash
# === STEP 1: Update Device Models (10 min) ===

vim nso_orchestration/automation/device_models.py
```

```python
# Update DeviceIntent to include nxos
class DeviceIntent(BaseModel):
    name: str
    device_type: Literal["ios", "ios-xe", "ios-xr", "nxos"]  # Added nxos
    # ... rest of fields
```

```bash
# === STEP 2: Create NX-OS Templates (30 min) ===

mkdir -p nso_orchestration/templates/nxos

vim nso_orchestration/templates/nxos/bgp_service.xml.j2
```

```xml
<!-- NX-OS BGP Template -->
<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <System xmlns="http://cisco.com/ns/yang/cisco-nx-os-device">
    <bgp-items>
      <inst-items>
        <asn>{{ local_as }}</asn>
        <dom-items>
          <Dom-list>
            <name>default</name>
            {% if router_id %}
            <rtrId>{{ router_id }}</rtrId>
            {% endif %}
            <af-items>
              <DomAf-list>
                <type>ipv4-ucast</type>
              </DomAf-list>
            </af-items>
            <peer-items>
              {% for neighbor in neighbors %}
              <Peer-list>
                <addr>{{ neighbor.neighbor_ip }}</addr>
                <asn>{{ neighbor.remote_as }}</asn>
                {% if neighbor.description %}
                <descr>{{ neighbor.description }}</descr>
                {% endif %}
                {% if neighbor.update_source %}
                <srcIf>{{ neighbor.update_source }}</srcIf>
                {% endif %}
                <af-items>
                  <PeerAf-list>
                    <type>ipv4-ucast</type>
                  </PeerAf-list>
                </af-items>
              </Peer-list>
              {% endfor %}
            </peer-items>
          </Dom-list>
        </dom-items>
      </inst-items>
    </bgp-items>
  </System>
</config>
```

```bash
# === STEP 3: Update Service Functions (20 min) ===

vim nso_orchestration/services/bgp_peering.py
```

```python
def deploy_bgp_service(
    client: NSOClient,
    device_name: str,
    intent: BGPPeeringServiceIntent,
    dry_run: bool = False,
    inventory=None
) -> tuple[bool, str]:
    
    # ... existing code ...
    
    # Select template based on device type
    if device and device.device_type == "ios-xr":
        template_name = "ios-xr/bgp_service.xml.j2"
        url_suffix = "/router/bgp"
    elif device and device.device_type == "nxos":  # NEW
        template_name = "nxos/bgp_service.xml.j2"
        url_suffix = "/System/bgp-items"
    else:
        template_name = "ios-xe/bgp_service.xml.j2"
        url_suffix = "/router"
    
    # ... rest of function ...
```

```bash
# === STEP 4: Update Inventory (5 min) ===

vim inventory/hosts.yaml
```

```yaml
# Add NX-OS device
dist-sw01:
  hostname: dist-sw01
  ip_address: 10.10.20.177
  device_type: nxos  # NX-OS device
  protocol: ssh
  groups:
    - distribution
    - switch
    - production
  vars:
    loopback0_ip: 10.101.101.1
    bgp_router_id: 10.101.101.1
    bgp_as: 65001
```

```bash
# === STEP 5: Create Intent (5 min) ===

vim intent/device_bgp_configs.yaml
```

```yaml
devices:
  # ... existing devices ...
  
  # NX-OS device
  - name: dist-sw01
    device_type: nxos
    delete_unmanaged_bgp_neighbors: false
    bgp:
      asn: 65001
      router_id: 10.101.101.1
      neighbors:
        - ip: 10.100.100.1
          remote_asn: 65001
          description: "iBGP to dist-rtr01"
```

```bash
# === STEP 6: Test (30 min) ===

# 1. Validate template renders correctly
python -c "
from nso_orchestration.automation.template_renderer import render_template

xml = render_template(
    'nxos/bgp_service.xml.j2',
    local_as=65001,
    router_id='10.101.101.1',
    neighbors=[{
        'neighbor_ip': '10.100.100.1',
        'remote_as': 65001,
        'description': 'Test neighbor'
    }]
)

print(xml)
"

# 2. Dry-run deployment
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-sw01 \
  --dry-run

# 3. Deploy
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-sw01

# 4. Verify idempotency
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dist-sw01
# Expected: "✓ No changes needed"
```

**Checklist**:
- ✅ Device type added to Literal type
- ✅ Templates created for new device type
- ✅ Service functions updated to handle new type
- ✅ Inventory updated with new device
- ✅ Intent file includes new device
- ✅ Template rendering tested
- ✅ Deployment tested
- ✅ Idempotency verified

**Common Issues with New Device Types**:
- **Different XML namespace**: Each NED has different namespace (urn:ios vs cisco-nx-os)
- **Different data model**: Structure varies (IOS uses "router/bgp", NX-OS uses "System/bgp-items")
- **Different field names**: "neighbor" vs "Peer-list", "asn" vs "as-no"
- **Different config syntax**: Some features not available on all platforms

---

### Testing New Features

**Approach**: Test-Driven Development (TDD) workflow

**Timeline**: 30-60 minutes per feature

**Steps**:

```bash
# === STEP 1: Write Failing Test First (10 min) ===

vim tests/test_new_feature.py
```

```python
"""Tests for new feature."""

import pytest
from nso_orchestration.automation.device_models import NewFeatureIntent

def test_new_feature_validation():
    """Test that new feature validates correctly."""
    # This test will FAIL initially (feature doesn't exist yet)
    intent = NewFeatureIntent(
        field1="value1",
        field2=123
    )
    
    assert intent.field1 == "value1"
    assert intent.field2 == 123

def test_new_feature_invalid_input():
    """Test that invalid input is rejected."""
    with pytest.raises(ValueError):
        NewFeatureIntent(
            field1="invalid",
            field2=-1  # Should be positive
        )

@pytest.mark.nso
def test_deploy_new_feature(nso_client, test_device):
    """Test deployment of new feature."""
    from nso_orchestration.services.new_feature import deploy_new_feature
    
    intent = NewFeatureIntent(field1="test", field2=100)
    
    # Deploy
    success, message = deploy_new_feature(nso_client, test_device, intent)
    assert success, message
    
    # Verify idempotency
    success2, message2 = deploy_new_feature(nso_client, test_device, intent)
    assert success2
    assert "Already configured" in message2
```

```bash
# Run test (should FAIL)
pytest tests/test_new_feature.py -v
# Expected: ImportError or AttributeError
```

```bash
# === STEP 2: Implement Minimum Code (20 min) ===

# Create models
vim nso_orchestration/automation/device_models.py
```

```python
class NewFeatureIntent(BaseModel):
    """Intent for new feature."""
    field1: str
    field2: int = Field(..., ge=0)  # Must be non-negative
```

```bash
# Create service
vim nso_orchestration/services/new_feature.py
```

```python
def deploy_new_feature(client, device_name, intent):
    """Deploy new feature."""
    # Minimal implementation to pass test
    return True, "Feature deployed"
```

```bash
# Run test again
pytest tests/test_new_feature.py -v
# Should pass now (or at least progress further)
```

```bash
# === STEP 3: Implement Full Feature (20 min) ===

# Add template, service logic, engine integration, etc.
# Following patterns from "Adding a New Resource Type" section above

# === STEP 4: Add Integration Tests (10 min) ===

vim tests/test_new_feature.py
```

```python
@pytest.mark.nso
@pytest.mark.integration
def test_new_feature_full_cycle(nso_client, test_device, clean_new_feature):
    """Test full deployment cycle."""
    intent = NewFeatureIntent(field1="production", field2=200)
    
    # Register for cleanup
    clean_new_feature.register("test_id")
    
    # Deploy
    success, msg = deploy_new_feature(nso_client, test_device, intent)
    assert success
    
    # Verify on device
    client.sync_from_device(test_device)
    config = client.get_device_config(test_device)
    # ... verify config contains expected values ...
    
    # Test idempotency
    success2, msg2 = deploy_new_feature(nso_client, test_device, intent)
    assert "Already configured" in msg2
    
    # Modify and redeploy
    intent.field2 = 300
    success3, msg3 = deploy_new_feature(nso_client, test_device, intent)
    assert success3
    
    # Cleanup happens automatically via fixture
```

```bash
# === STEP 5: Run Full Test Suite (5 min) ===

# Unit tests only
pytest tests/test_new_feature.py -v -m unit

# Integration tests (requires NSO)
pytest tests/test_new_feature.py -v -m nso

# All tests
pytest tests/test_new_feature.py -v
```

**TDD Benefits**:
- ✅ Forces clear requirements (write test first)
- ✅ Prevents over-engineering (only write code to pass tests)
- ✅ Built-in regression testing (tests fail if feature breaks)
- ✅ Documentation via tests (tests show how to use feature)
- ✅ Confidence in refactoring (tests catch breaking changes)

**Testing Best Practices**:
1. **Test one thing per test**: Keep tests focused and small
2. **Use descriptive names**: `test_bgp_neighbor_addition` not `test_1`
3. **Arrange-Act-Assert**: Clear test structure
4. **Use fixtures**: Reduce duplication with pytest fixtures
5. **Mock external dependencies**: Don't test NSO's API, test your code
6. **Test edge cases**: Negative numbers, empty lists, None values
7. **Test error handling**: Ensure errors are caught and logged

---

## Summary

This workflow document complements the ARCHITECTURE.md by providing:

✅ **User Journeys**: Step-by-step guides for common tasks
✅ **Process Flows**: Detailed internal workflows with diagrams
✅ **Decision Trees**: When to use what approach
✅ **Common Scenarios**: Real-world examples with code
✅ **Troubleshooting**: Diagnosis and solutions for common issues
✅ **Development Workflows**: How to extend the framework

**Quick Reference**:

| I want to... | See section... |
|--------------|----------------|
| Deploy BGP for first time | [New User: First Deployment](#new-user-first-deployment) |
| Add a new router | [Regular User: Adding a New Device](#regular-user-adding-a-new-device) |
| Modify existing config | [Regular User: Modifying BGP Configuration](#regular-user-modifying-bgp-configuration) |
| Deploy multiple resources | [Advanced User: Multi-Resource Deployment](#advanced-user-multi-resource-deployment) |
| Understand what happens internally | [Flow 1: BGP Deployment from Scratch](#flow-1-bgp-deployment-from-scratch) |
| Migrate from manual configs | [Scenario 3: Migrating from Manual to Automation](#scenario-3-migrating-from-manual-to-automation) |
| Fix connection issues | [NSO Connection Issues](#nso-connection-issues) |
| Fix validation errors | [Validation Errors](#validation-errors) |
| Add new resource type (OSPF, etc.) | [Adding a New Resource Type](#adding-a-new-resource-type) |
| Support new device type (NX-OS, etc.) | [Adding Support for New Device Type](#adding-support-for-new-device-type) |

**Next Steps**:
1. Review ARCHITECTURE.md for technical details on each component
2. Follow Quick Start guide for initial setup
3. Try User Journeys examples hands-on
4. Use Troubleshooting Guide as needed
5. Extend framework with Development Workflows

---

**Built with ❤️ for network automation**