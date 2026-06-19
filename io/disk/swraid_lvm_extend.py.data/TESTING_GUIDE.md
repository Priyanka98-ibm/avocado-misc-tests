# Software RAID Rebuild + Sync + LVM Extend - Testing Guide

## Files Created

### 1. Test Script
**Location:** `io/disk/swraid_lvm_extend.py`
- Main test implementation
- Contains all test logic for RAID rebuild, sync, and LVM extend

### 2. Configuration File
**Location:** `io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml`
- YAML configuration with multiple test scenarios
- Defines disk configurations, RAID levels, and filesystem types

### 3. Documentation
**Location:** `io/disk/swraid_lvm_extend.py.data/README.md`
- Comprehensive documentation
- Usage examples and troubleshooting guide

---

## Pre-Test Setup

### 1. Verify File Structure
```bash
cd /Users/priyankabehera/Desktop/GIT/avocado-misc-tests/io/disk

# Check files exist
ls -la swraid_lvm_extend.py
ls -la swraid_lvm_extend.py.data/swraid_lvm_extend.yaml
ls -la swraid_lvm_extend.py.data/README.md
```

### 2. Prepare Test Disks

**IMPORTANT:** Replace disk names in YAML file with your actual available disks!

```bash
# List available disks
lsblk

# Example output:
# sdb    8:16   0  100G  0 disk
# sdc    8:32   0  100G  0 disk
# sdd    8:48   0  100G  0 disk
```

**Edit the YAML file** to use your actual disk names:
```bash
vi swraid_lvm_extend.py.data/swraid_lvm_extend.yaml
```

### 3. Ensure Disks are Clean
```bash
# WARNING: This will destroy data on the disks!
# Make sure disks are not in use

# Check if disks are mounted
mount | grep sdb
mount | grep sdc

# Unmount if needed
umount /dev/sdb1
umount /dev/sdc1

# Remove any existing RAID signatures
mdadm --zero-superblock /dev/sdb
mdadm --zero-superblock /dev/sdc

# Remove any LVM signatures
wipefs -a /dev/sdb
wipefs -a /dev/sdc
```

---

## Test Execution Commands

### Test 1: Basic RAID1 with ext4 (Recommended for first test)

```bash
cd /Users/priyankabehera/Desktop/GIT/avocado-misc-tests

avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic
```

**Expected Duration:** 5-15 minutes (depending on disk sync speed)

**What this test does:**
1. Creates RAID1 array with 2 disks
2. Waits for initial sync
3. Removes one disk and adds it back (rebuild test)
4. Creates LVM on RAID device
5. Extends the logical volume
6. Cleans up everything

---

### Test 2: RAID5 with 3 disks and spare

```bash
avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_raid5
```

**Requirements:** 4 disks (3 for RAID5 + 1 spare)

---

### Test 3: RAID6 with 4 disks

```bash
avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_raid6
```

**Requirements:** 5 disks (4 for RAID6 + 1 spare)

---

### Test 4: RAID10 with 4 disks

```bash
avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_raid10
```

**Requirements:** 4 disks

---

### Test 5: RAID1 with XFS filesystem

```bash
avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_xfs
```

**Requirements:** 2 disks + xfsprogs package

---

### Test 6: Custom Configuration (Override parameters)

```bash
avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic \
    -p disks='sdb sdc sdd' \
    -p raid='5' \
    -p fs='xfs'
```

---

## Monitoring Test Progress

### In Another Terminal - Monitor RAID Status

```bash
# Watch RAID sync progress
watch -n 2 'cat /proc/mdstat'

# Or detailed status
watch -n 2 'mdadm --detail /dev/md/test_raid'
```

### Monitor LVM Operations

```bash
# Watch volume groups
watch -n 2 'vgdisplay'

# Watch logical volumes
watch -n 2 'lvdisplay'

# Watch disk usage
watch -n 2 'df -h'
```

---

## Expected Test Output

### Successful Test Output Should Show:

```
TEST 1: RAID Creation and Synchronization
============================================================
RAID array /dev/md/test_raid created successfully
Waiting for RAID synchronization to complete...
RAID synchronization completed successfully

TEST 2: RAID Rebuild and Sync
============================================================
Removing disk /dev/sdc from RAID...
Adding disk /dev/sdc back to RAID...
RAID rebuild completed successfully

TEST 3: LVM Setup on RAID
============================================================
Creating Volume Group test_vg on /dev/md/test_raid...
Creating Logical Volume test_lv...
Creating ext4 filesystem and mounting...

TEST 4: LVM Extend
============================================================
Extending test_lv by 20% of VG...
Resizing ext4 filesystem...
LVM extend completed successfully

All tests completed successfully!
```

---

## Troubleshooting

### Issue 1: Disks Not Found
```bash
# Error: "No disks provided for RAID creation"
# Solution: Edit YAML file with correct disk names

vi io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml
# Change: disks: 'sdb sdc'
# To your actual disks: disks: 'nvme0n1 nvme0n2'
```

### Issue 2: Disks Already in Use
```bash
# Error: "Device or resource busy"
# Solution: Clean up existing RAID/LVM

# Stop any existing RAID
mdadm --stop /dev/md/test_raid
mdadm --stop /dev/md127  # or whatever md device exists

# Remove LVM
lvremove -f /dev/test_vg/test_lv
vgremove -f test_vg
pvremove /dev/sdb /dev/sdc

# Clean superblocks
mdadm --zero-superblock /dev/sdb /dev/sdc
wipefs -a /dev/sdb /dev/sdc
```

### Issue 3: Sync Timeout
```bash
# Error: "RAID sync did not complete within 600 seconds"
# Solution: Large disks may take longer

# Check sync progress
cat /proc/mdstat

# If sync is progressing but slow, you can:
# 1. Wait for it to complete naturally
# 2. Speed up sync (may impact system performance)
echo 200000 > /proc/sys/dev/raid/speed_limit_min
```

### Issue 4: Permission Denied
```bash
# Error: "Permission denied"
# Solution: Run with sudo

sudo avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic
```

### Issue 5: Package Not Installed
```bash
# Error: "Unable to install mdadm" or "Unable to install lvm2"
# Solution: Install manually

# For RHEL/CentOS/Fedora
sudo dnf install mdadm lvm2 xfsprogs

# For Ubuntu/Debian
sudo apt-get install mdadm lvm2 xfsprogs

# For SLES
sudo zypper install mdadm lvm2 xfsprogs
```

---

## Verification After Test

### Check Cleanup Was Successful

```bash
# No RAID devices should exist
cat /proc/mdstat
# Should show: "Personalities :" with no active arrays

# No test volume groups
vgs | grep test_vg
# Should return nothing

# No test logical volumes
lvs | grep test_lv
# Should return nothing

# Disks should be clean
lsblk
# Your test disks should show no partitions or mounts
```

---

## Test Results Location

```bash
# Avocado stores results in:
ls -la ~/avocado/job-results/latest/

# View test log
cat ~/avocado/job-results/latest/job.log

# View detailed test output
cat ~/avocado/job-results/latest/test-results/*/debug.log
```

---

## Quick Test Checklist

- [ ] Files exist (swraid_lvm_extend.py, .yaml, README.md)
- [ ] YAML file updated with correct disk names
- [ ] Disks are available and not in use
- [ ] Disks are cleaned (no existing RAID/LVM signatures)
- [ ] Required packages installed (mdadm, lvm2)
- [ ] Running with appropriate permissions (root/sudo)
- [ ] Test executed successfully
- [ ] All 4 test phases completed
- [ ] Cleanup verified (no leftover RAID/LVM)

---

## Ready for PR?

Once all tests pass successfully:

1. ✅ Test runs without errors
2. ✅ All 4 test phases complete
3. ✅ RAID rebuild works correctly
4. ✅ LVM extend works correctly
5. ✅ Cleanup is successful
6. ✅ Test can be repeated multiple times

**Then proceed with creating the PR!**

---

## Contact

If you encounter any issues during testing, check:
1. System logs: `journalctl -xe`
2. RAID logs: `dmesg | grep md`
3. LVM logs: `dmesg | grep lvm`
4. Test debug logs in avocado results directory

---

## Summary Command for Quick Testing

```bash
# Navigate to test directory
cd /Users/priyankabehera/Desktop/GIT/avocado-misc-tests

# Run basic test (RECOMMENDED FOR FIRST TEST)
sudo avocado run --max-parallel-tasks=1 \
    io/disk/swraid_lvm_extend.py \
    -m io/disk/swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic \
    --show-job-log

# The --show-job-log flag will display output in real-time
```

**Good luck with testing! 🚀**