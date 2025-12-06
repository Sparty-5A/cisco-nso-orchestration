# QUICK START - 10-Minute Guide

**Get from zero to deploying BGP configurations in 10 minutes**

This guide gets you up and running quickly. For detailed explanations, see [WORKFLOW.md](WORKFLOW.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

---

## ⏱️ Time Commitment

- **Setup**: 3 minutes
- **First Deployment**: 5 minutes
- **Verification**: 2 minutes

**Total**: 10 minutes

---

## 📋 Prerequisites (2 minutes to verify)

```bash
# 1. Python 3.12+
python --version
# Expected: Python 3.12.x or higher

# 2. Access to Cisco NSO
# DevNet Sandbox: https://devnetsandbox.cisco.com/
# Or your own NSO instance

# 3. VPN connected (if using DevNet Sandbox)
# Follow sandbox instructions to connect

# 4. Git repository cloned
git clone https://github.com/yourusername/Scott_NetEng_project.git
cd Scott_NetEng_project/nso_orchestration
```

✅ **Ready?** Let's go!

---

## 🚀 Part 1: Setup (3 minutes)

### Step 1: Install Dependencies (1 min)

```bash
pip install -r requirements.txt
```

**Expected output**:
```
Successfully installed pydantic loguru httpx pyyaml python-decouple jinja2
```

### Step 2: Configure NSO Connection (1 min)

**Option A: Use Defaults (DevNet Sandbox)**
```bash
# These are already configured as defaults:
# NSO_HOST=10.10.20.49
# NSO_PORT=8080
# NSO_USER=developer
# NSO_PW=C1sco12345

# Skip to Step 3!
```

**Option B: Custom NSO Instance**
```bash
export NSO_HOST=your-nso-host
export NSO_PORT=8080
export NSO_USER=your-username
export NSO_PW=your-password
```

### Step 3: Verify NSO Connection (1 min)

```bash
python scripts/sync_devices.py
```

**Expected output**:
```
Connecting to NSO at 10.10.20.49
✓ NSO health check passed
Found 12 devices to sync
Syncing edge-firewall01...
✓ Synced successfully
...
Sync complete: 12 succeeded, 0 failed
```

✅ **Checkpoint**: NSO connected and devices synced

---

## 🎯 Part 2: Your First Deployment (5 minutes)

### Step 4: Review What You're Deploying (1 min)

```bash
cat intent/device_bgp_configs.yaml
```

**Key sections to notice**:
```yaml
devices:
  - name: dev-dist-rtr01           # Device name
    device_type: ios-xe            # Platform
    delete_unmanaged_bgp_neighbors: false  # Safe mode
    bgp:
      asn: 65001                   # BGP AS number
      router_id: 10.100.100.2      # Unique router ID
      neighbors:
        - ip: 10.200.200.2         # Neighbor IP
          remote_asn: 65001        # Neighbor AS
          description: "iBGP to dev-core-rtr01"
```

**What this does**: Configures BGP on `dev-dist-rtr01` with one iBGP neighbor.

### Step 5: Preview Changes (DRY-RUN) (2 min)

**Always preview first!**

```bash
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run
```

**Expected output**:
```
======================================================================
DRY-RUN: Applying network intent
======================================================================
Calculating changes for dev-dist-rtr01
[dev-dist-rtr01] Querying current BGP configuration
[dev-dist-rtr01] No BGP configuration found

Planned changes: 1 total
  - 1 creates

[DRY-RUN] Would apply: [dev-dist-rtr01] CREATE bgp 65001

======================================================================
DRY-RUN Complete: 1 changes would be applied
======================================================================
```

**Good signs**:
- ✅ "Planned changes: 1 total"
- ✅ "CREATE bgp 65001"
- ✅ No errors

**If you see "No changes needed"**: BGP already configured (skip to Step 7)

### Step 6: Deploy for Real (1 min)

**Remove --dry-run to actually deploy**:

```bash
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01
```

**Expected output**:
```
======================================================================
Applying network intent
======================================================================
Calculating changes for dev-dist-rtr01
Planned changes: 1 total
  - 1 creates

Applying: [dev-dist-rtr01] CREATE bgp 65001
[dev-dist-rtr01] Deploying BGP peering service
[dev-dist-rtr01] ✓ BGP service deployed successfully

======================================================================
Intent reconciliation complete: 1 succeeded, 0 failed
======================================================================
```

**Good signs**:
- ✅ "1 succeeded, 0 failed"
- ✅ "BGP service deployed successfully"

### Step 7: Verify Idempotency (1 min)

**Run the same command again** (should show no changes):

```bash
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01
```

**Expected output**:
```
======================================================================
Applying network intent
======================================================================
Calculating changes for dev-dist-rtr01
[dev-dist-rtr01] BGP AS 65001 already configured correctly

✓ No changes needed - network is in desired state
======================================================================
```

**This proves**:
- ✅ Idempotency works (safe to run repeatedly)
- ✅ Framework detects current state correctly
- ✅ No unnecessary changes applied

✅ **Checkpoint**: BGP deployed successfully and idempotency verified!

---

## ✅ Part 3: Verification (2 minutes)

### Step 8: Verify on Device (Optional)

If you have direct SSH access to the device:

```bash
ssh cisco@dev-dist-rtr01

# Check BGP configuration
show running-config | section router bgp

# Check BGP summary
show ip bgp summary

# Check BGP neighbors
show ip bgp neighbors
```

**Expected BGP config**:
```
router bgp 65001
 bgp router-id 10.100.100.2
 neighbor 10.200.200.2 remote-as 65001
 neighbor 10.200.200.2 description iBGP to dev-core-rtr01
 neighbor 10.200.200.2 update-source Loopback0
```

### Step 9: What You Just Did

🎉 **Congratulations!** In 10 minutes you:

1. ✅ Installed the framework
2. ✅ Connected to NSO
3. ✅ Deployed BGP configuration via automation
4. ✅ Verified idempotency (no unnecessary changes)
5. ✅ Used infrastructure-as-code principles

**Key Concepts Demonstrated**:
- **Declarative**: You declared desired state (intent), framework handled the "how"
- **Idempotent**: Running twice = same result (safe for automation)
- **Safe by Default**: --dry-run prevents accidents

---

## 🎓 What's Next?

### Immediate Next Steps (10-15 min each)

**1. Deploy Loopback Interfaces**
```bash
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --device dev-dist-rtr01 \
  --dry-run

# Review, then deploy without --dry-run
```

**2. Deploy Both Loopbacks + BGP Together**
```bash
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01 \
  --dry-run
```

**3. Modify BGP Configuration**
```bash
# Edit intent file
vim intent/device_bgp_configs.yaml

# Add a new neighbor, then deploy
python scripts/apply_device_intent.py \
  --intent intent/device_bgp_configs.yaml \
  --device dev-dist-rtr01
```

### Learning Path (1-2 hours)

1. **Read [WORKFLOW.md](WORKFLOW.md)** - Detailed user journeys and scenarios
2. **Read [ARCHITECTURE.md](ARCHITECTURE.md)** - Technical deep dive
3. **Explore Intent Files** - Understand YAML structure
4. **Check Inventory System** - See variable inheritance
5. **Run Tests** - `pytest tests/ -v`

### Hands-On Practice (2-3 hours)

**Beginner Exercises**:
1. Add a new loopback interface to dev-dist-rtr01
2. Add a second BGP neighbor
3. Deploy to a different device (dev-core-rtr01)

**Intermediate Exercises**:
1. Add a new device to inventory and deploy configs
2. Test safe mode vs strict mode for deletion
3. Create a custom intent file for your network

**Advanced Exercises**:
1. Add OSPF support (follow [WORKFLOW.md](WORKFLOW.md))
2. Add support for NX-OS devices
3. Write tests for new features

---

## 🆘 Quick Troubleshooting

### Issue: "NSO health check failed"

**Solution**:
```bash
# Check VPN connected
ping 10.10.20.49

# Verify environment variables
echo "NSO_HOST=$NSO_HOST"

# Try explicit connection
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient(host='10.10.20.49')
print('✓ Connected' if client.health_check() else '✗ Failed')
"
```

### Issue: "ValidationError: Invalid IP address"

**Solution**:
```bash
# Check YAML syntax
python -c "
import yaml
with open('intent/device_bgp_configs.yaml') as f:
    yaml.safe_load(f)
print('✓ YAML valid')
"

# Fix IP addresses (must be valid format)
vim intent/device_bgp_configs.yaml
```

### Issue: "Device not found in NSO"

**Solution**:
```bash
# Sync devices first
python scripts/sync_devices.py

# Verify device exists
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('10.10.20.49')
devices = client.get_devices()
print(f'Available devices: {devices}')
"
```

### Issue: "Already configured - no changes needed" (but you expected changes)

**This is normal!** It means:
- ✅ Configuration already matches your intent
- ✅ Idempotency working correctly
- ✅ Safe to run automation repeatedly

**To see it work**: Modify the intent file, then deploy again.

---

## 📊 Quick Reference Commands

### Essential Commands

```bash
# Sync all devices from NSO
python scripts/sync_devices.py

# Preview changes (DRY-RUN)
python scripts/apply_device_intent.py \
  --intent intent/FILENAME.yaml \
  --device DEVICE_NAME \
  --dry-run

# Deploy changes
python scripts/apply_device_intent.py \
  --intent intent/FILENAME.yaml \
  --device DEVICE_NAME

# Deploy to all devices in intent
python scripts/apply_device_intent.py \
  --intent intent/FILENAME.yaml

# Verbose output (debugging)
python scripts/apply_device_intent.py \
  --intent intent/FILENAME.yaml \
  --device DEVICE_NAME \
  --verbose

# Multiple intent files
python scripts/apply_device_intent.py \
  --intent intent/device_loopbacks.yaml \
  --intent intent/device_bgp_configs.yaml \
  --device DEVICE_NAME
```

### Useful Shortcuts

```bash
# Quick validation test
python -c "
from nso_orchestration.automation.device_models import NetworkIntent
import yaml
with open('intent/device_bgp_configs.yaml') as f:
    intent = NetworkIntent(**yaml.safe_load(f))
print('✓ Intent valid')
"

# Check device in inventory
python -c "
from nso_orchestration.automation.inventory_loader import load_inventory
inv = load_inventory()
device = inv.get_device('dev-dist-rtr01')
print(f'Type: {device.device_type}')
print(f'Groups: {device.groups}')
"

# List all devices in NSO
python -c "
from nso_orchestration.automation.nso_client import NSOClient
client = NSOClient('10.10.20.49')
print(client.get_devices())
"
```

---

## 🎯 Success Checklist

After completing this quick start, you should have:

- ✅ Framework installed and working
- ✅ NSO connection verified
- ✅ First BGP deployment successful
- ✅ Idempotency verified (ran twice, no changes second time)
- ✅ Understanding of basic workflow (intent → dry-run → deploy)
- ✅ Confidence to try next steps

---

## 📚 Additional Resources

**Documentation**:
- [WORKFLOW.md](WORKFLOW.md) - Detailed workflows and scenarios
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical deep dive
- [README.md](README.md) - Project overview and features

**Intent Files** (templates to modify):
- `intent/device_loopbacks.yaml` - Loopback interface configs
- `intent/device_bgp_configs.yaml` - BGP routing configs

**Inventory Files** (device metadata):
- `inventory/hosts.yaml` - Device definitions
- `inventory/groups.yaml` - Group definitions
- `inventory/defaults.yaml` - Default values

**Code Examples**:
- `scripts/apply_device_intent.py` - Main deployment script
- `nso_orchestration/automation/device_engine.py` - Reconciliation engine
- `nso_orchestration/services/bgp_peering.py` - BGP deployment logic

---

## 💬 Common Questions

**Q: Is it safe to run on production devices?**
A: Use `--dry-run` first, test on dev devices, and keep `delete_unmanaged=false` (safe mode).

**Q: What if I make a mistake in the intent file?**
A: Pydantic validation catches most errors before deployment. Always use `--dry-run`.

**Q: Can I rollback if something goes wrong?**
A: Yes! NSO keeps rollback files. See [WORKFLOW.md - Troubleshooting](WORKFLOW.md#deployment-failures).

**Q: How do I add a new device?**
A: See [WORKFLOW.md - Adding a New Device](WORKFLOW.md#regular-user-adding-a-new-device).

**Q: Can I deploy to multiple devices at once?**
A: Yes! Omit `--device` flag to deploy to all devices in intent file.

**Q: What does "idempotent" mean?**
A: Running the same deployment multiple times produces the same result (no unnecessary changes).

**Q: What's the difference between safe mode and strict mode?**
A: Safe mode (default) ignores unmanaged configs. Strict mode deletes them. See [WORKFLOW.md - Decision Trees](WORKFLOW.md#safe-mode-vs-strict-mode).

---

## 🎉 You're Ready!

You've completed the quick start and deployed your first automated network configuration!

**Next**: Try the [User Journeys in WORKFLOW.md](WORKFLOW.md#user-journeys) or explore the [Architecture Documentation](ARCHITECTURE.md).

**Need Help?** 
- Review [Troubleshooting Guide](WORKFLOW.md#troubleshooting-guide)
- Check [Common Scenarios](WORKFLOW.md#common-scenarios)
- Open an issue on GitHub

---

**Built with ❤️ for network automation**

*Time to complete: 10 minutes | Difficulty: Beginner | Prerequisites: Python 3.12+, NSO access*