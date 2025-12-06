# 🌐 Cisco NSO Network Orchestration Framework

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Cisco NSO](https://img.shields.io/badge/Cisco_NSO-Compatible-green.svg)](https://www.cisco.com/c/en/us/products/cloud-systems-management/network-services-orchestrator/index.html)
[![RESTCONF](https://img.shields.io/badge/Protocol-RESTCONF-orange)](https://tools.ietf.org/html/rfc8040)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-grade Infrastructure as Code framework for Cisco network orchestration using NSO. Features multi-platform support (IOS-XE, IOS-XR, NX-OS), intent-based configuration, reconciliation engine, and comprehensive testing. Built for Cisco DevNet Sandbox environments.

---

## ✨ Features

### Core Capabilities
- **Multi-Platform Support** - IOS-XE, IOS-XR, and NX-OS with platform-specific templates
- **Intent-Based Configuration** - Declarative YAML intent files with Pydantic validation
- **Reconciliation Engine** - Calculates minimal configuration diffs and applies only necessary changes
- **Idempotency** - Safe to run multiple times, only applies changes when needed
- **NSO Integration** - RESTCONF API communication with Cisco NSO

### Safety & Reliability
- **Safe Deletion Modes** - Configurable policies for managing untracked resources
- **Dry-Run Mode** - Preview changes before applying to production
- **Pre-Deployment Validation** - Schema validation and prerequisite checks
- **Configuration Backups** - NSO maintains rollback files automatically
- **Error Handling** - Graceful failure with detailed error messages

### Operations & Development
- **3-Tier Variable Inheritance** - Defaults → Groups → Hosts for DRY configuration
- **Inventory Management** - Centralized device metadata with group-based organization
- **Template System** - Jinja2 templates for platform-specific XML generation
- **Comprehensive Testing** - Unit and integration tests with pytest
- **CI/CD Ready** - GitHub Actions workflows for automated testing

---

## 🏗️ Architecture

### High-Level Design

```
┌────────────────────────────────────────────────────────────┐
│  INTENT LAYER                                              │
│  └─ YAML files (device_bgp_configs.yaml)                  │
│     Pydantic models (device_models.py)                     │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  INVENTORY LAYER                                           │
│  └─ Device inventory (hosts.yaml, groups.yaml)            │
│     3-tier variable inheritance                            │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  ORCHESTRATION LAYER                                       │
│  └─ Device engine (device_engine.py)                      │
│     Service orchestrator (service_orchestrator.py)         │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  SERVICE LAYER                                             │
│  └─ BGP peering (bgp_peering.py)                          │
│     Template renderer (template_renderer.py)               │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  NSO LAYER                                                 │
│  └─ RESTCONF client (nso_client.py)                       │
│     Device synchronization                                 │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  NETWORK DEVICES                                           │
│  └─ IOS-XE, IOS-XR, NX-OS                                 │
└────────────────────────────────────────────────────────────┘
```

### Network Topology

The framework orchestrates configurations across a Cisco DevNet Sandbox topology:

**Production Environment:**
- Core Layer: IOS-XR routers (core-rtr01)
- Distribution Layer: IOS-XE routers (dist-rtr01)
- Access Layer: NX-OS switches (dist-sw01)

**Development Environment:**
- Mirror topology for safe testing (dev-core-rtr01, dev-dist-rtr01, dev-dist-sw01)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- Access to Cisco NSO (DevNet Sandbox or local instance)
- VPN connection to DevNet Sandbox (if using sandbox)

### Installation

```bash
# Clone repository
git clone https://github.com/Sparty-5A/cisco-nso-orchestration.git
cd cisco-nso-orchestration

# Install dependencies
pip install -e ".[dev]"

# Configure NSO connection (DevNet Sandbox defaults)
export NSO_HOST=10.10.20.49
export NSO_PORT=8080
export NSO_USER=developer
export NSO_PW=C1sco12345

# Verify NSO connectivity
python scripts/sync_devices.py
```

### First Deployment

```bash
# Preview changes (dry-run)
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run

# Deploy BGP configuration
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01

# Verify idempotency (run again, should show no changes)
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01
```

---

## 📁 Project Structure

```
cisco-nso-orchestration/
├── automation/                  # Core automation engine
│   ├── device_engine.py        # Reconciliation & orchestration
│   ├── device_models.py        # Pydantic intent models
│   ├── inventory_loader.py     # Inventory management
│   ├── nso_client.py           # RESTCONF client
│   ├── service_orchestrator.py # Service-level orchestration
│   └── template_renderer.py    # Jinja2 template engine
│
├── services/                    # Service implementations
│   └── bgp_peering.py          # BGP deployment logic
│
├── templates/                   # Configuration templates
│   ├── ios-xe/                 # IOS-XE specific templates
│   │   └── bgp_service.xml.j2
│   └── ios-xr/                 # IOS-XR specific templates
│       └── bgp_service.xml.j2
│
├── scripts/                     # User interface scripts
│   ├── apply_device_intent.py  # Main deployment CLI
│   ├── deploy_service.py       # Service deployment CLI
│   ├── sync_devices.py         # NSO device sync
│   └── run_any_command.py      # Ad-hoc command execution
│
├── intent/                      # Intent definitions
│   ├── device_bgp_configs.yaml # BGP intent
│   └── device_loopbacks.yaml   # Loopback intent
│
├── inventory/                   # Device inventory
│   ├── hosts.yaml              # Device definitions
│   ├── groups.yaml             # Group definitions
│   └── defaults.yaml           # Default values
│
├── tests/                       # Test suite
│   ├── test_device_models.py   # Model validation tests
│   ├── test_template_renderer.py # Template tests
│   └── test_bgp_service.py     # Service logic tests
│
└── docs/                        # Documentation
    ├── ARCHITECTURE.md         # Architecture deep dive
    ├── QUICK_START.md          # 10-minute guide
    └── WORKFLOW.md             # Detailed workflows
```

---

## 💻 Usage Examples

### Device-Level Intent

```bash
# Deploy loopback interfaces
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --device dev-dist-rtr01

# Deploy BGP configuration
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01

# Combine multiple intents (merge configurations)
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01

# Deploy to all devices in intent file
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml
```

### Service-Level Intent

```bash
# Deploy BGP service to multiple devices
python scripts/deploy_service.py \
  --intent intent/service_bgp_peering.yaml \
  --dry-run

# Deploy with validation
python scripts/deploy_service.py \
  --intent intent/service_bgp_peering.yaml \
  --validate

# Deploy to inventory group
python scripts/deploy_service.py \
  --intent intent/service_bgp_peering.yaml \
  --group distribution
```

### NSO Operations

```bash
# Sync all devices from NSO
python scripts/sync_devices.py

# Run ad-hoc command
python scripts/run_any_command.py \
  --device dev-dist-rtr01 \
  --command "show ip bgp summary"
```

---

## 🔧 Configuration

### Intent File Format (Device-Level)

```yaml
devices:
  - name: dev-dist-rtr01
    device_type: ios-xe
    delete_unmanaged_loopbacks: false     # Safe mode
    delete_unmanaged_bgp_neighbors: false # Safe mode
    
    loopbacks:
      - id: 100
        ipv4: 10.100.100.1
        netmask: 255.255.255.255
        description: "Management loopback"
    
    bgp:
      asn: 65001
      router_id: 10.100.100.1
      neighbors:
        - ip: 10.200.200.1
          remote_asn: 65001
          description: "iBGP to core-rtr01"
          update_source: "Loopback0"
```

### Inventory Format

**hosts.yaml:**
```yaml
dev-dist-rtr01:
  mgmt_ip: 10.10.20.176
  device_type: ios-xe
  groups: [distribution, development]
  platform: cisco-iosxe
```

**groups.yaml:**
```yaml
distribution:
  vars:
    role: distribution
    ospf_area: 0
```

**defaults.yaml:**
```yaml
vars:
  dns_servers: [8.8.8.8, 8.8.4.4]
  ntp_servers: [10.10.20.1]
```

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit
pytest -m integration

# Run with coverage
pytest --cov=automation --cov=services --cov-report=html

# Run specific test file
pytest tests/test_device_models.py -v
```

### Test Coverage

- **Unit Tests** - Pydantic model validation, template rendering
- **Integration Tests** - Service deployment logic, NSO communication (mocked)
- **Validation Tests** - Intent file validation, inventory validation

---

## 🛡️ Safety Features

### Deletion Policies

```yaml
# SAFE MODE (default) - Recommended for production
delete_unmanaged_bgp_neighbors: false
# Only manages declared neighbors, ignores others

# STRICT MODE - Use with caution
delete_unmanaged_bgp_neighbors: true
# Deletes any BGP neighbors NOT in intent
```

### Dry-Run Mode

Always preview changes before applying:

```bash
# Preview changes
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --dry-run

# Review output, then deploy
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml
```

### Reconciliation Engine

```python
# 1. Query current device state via NSO
current_config = nso_client.get_bgp_config(device)

# 2. Compare with intent
if is_configured(current_config, intent):
    return "SKIPPED - Already configured"

# 3. Calculate minimal diff
changes = calculate_diff(current_config, intent)

# 4. Apply only necessary changes
nso_client.apply_config(changes)
```

---

## 🎯 Multi-Platform Support

### Platform Differences Abstracted

**IOS-XE Template (XML):**
```xml
<config xmlns="http://tail-f.com/ns/config/1.0">
  <devices xmlns="http://tail-f.com/ns/ncs">
    <device>
      <name>{{ device_name }}</name>
      <config>
        <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
          <router>
            <bgp xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-bgp">
              <!-- IOS-XE specific structure -->
            </bgp>
          </router>
        </native>
      </config>
    </device>
  </devices>
</config>
```

**IOS-XR Template (XML):**
```xml
<config xmlns="http://tail-f.com/ns/config/1.0">
  <devices xmlns="http://tail-f.com/ns/ncs">
    <device>
      <name>{{ device_name }}</name>
      <config>
        <router xmlns="http://tail-f.com/ned/cisco-ios-xr">
          <bgp>
            <!-- IOS-XR specific structure -->
          </bgp>
        </router>
      </config>
    </device>
  </devices>
</config>
```

**Framework automatically selects correct template based on `device_type`!**

---

## 📊 Key Design Patterns

### 3-Tier Variable Inheritance

```python
# Resolution order: defaults → groups → hosts
final_vars = {
    **defaults.vars,           # Layer 1: Global defaults
    **group1.vars,             # Layer 2: Group-level
    **group2.vars,
    **host.vars                # Layer 3: Host-specific (highest priority)
}
```

### Query-Augmented Intent

Users provide minimal intent:
```yaml
bgp:
  asn: 65001
  router_id: 10.100.100.1
```

Framework queries NSO for related config and builds complete context for templates.

### Idempotency

```python
def is_configured(current, intent) -> bool:
    """Check if device already matches intent."""
    if current.asn != intent.asn:
        return False
    if current.router_id != intent.router_id:
        return False
    # ... more checks
    return True  # No changes needed
```

---

## 📚 Additional Documentation

- [Architecture Deep Dive](docs/ARCHITECTURE.md) - Complete technical architecture
- [Quick Start Guide](docs/QUICK_START.md) - 10-minute getting started
- [Workflow Documentation](docs/WORKFLOW.md) - Detailed user journeys
- [Portfolio Polish](docs/PORTFOLIO_POLISH.md) - Showcase tips

---

## 🎓 Technologies Used

- **Python 3.12+** - Modern Python with type hints
- **Cisco NSO** - Network Services Orchestrator
- **RESTCONF** - RESTful API for network management
- **Pydantic** - Data validation and settings management
- **Jinja2** - Template engine for XML generation
- **pytest** - Testing framework
- **PyYAML** - YAML parsing
- **Loguru** - Modern logging
- **httpx** - Async HTTP client

---

## 🤝 Contributing

This is a portfolio project demonstrating production-grade network automation practices. Contributions and feedback welcome!

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .

# Lint code
ruff check .
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built for [Cisco DevNet Sandbox](https://devnetsandbox.cisco.com/)
- Uses Cisco NSO for network orchestration
- Inspired by infrastructure-as-code principles from Terraform and Ansible

---

## 📞 Contact

**Author**: Scott Penry  
**Email**: scottpenry@comcast.net  
**GitHub**: [@Sparty-5A](https://github.com/Sparty-5A)

---

## ⭐ Show Your Support

Give a ⭐️ if this project helped you!

---

**Built for production network automation** | **Multi-platform Cisco orchestration** | **Intent-based configuration**