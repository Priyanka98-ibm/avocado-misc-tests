# Software RAID Rebuild + Sync + LVM Extend Test

## Overview

This test suite provides comprehensive testing for Software RAID (mdadm) rebuild, synchronization, and LVM (Logical Volume Manager) extend operations. It validates the complete workflow of creating a RAID array, setting up LVM on top of it, performing RAID rebuild operations, and extending logical volumes.

## Test Components

### 1. RAID Creation and Synchronization
- Creates a software RAID array using mdadm
- Monitors initial synchronization progress
- Verifies RAID array status and integrity

### 2. RAID Rebuild Testing
- Removes a disk from the RAID array (simulating disk failure)
- Re-adds the disk to trigger rebuild
- Monitors rebuild/resync progress
- Validates RAID integrity after rebuild

### 3. LVM Setup on RAID
- Creates Physical Volume (PV) on RAID device
- Creates Volume Group (VG)
- Creates Logical Volume (LV) using 50% of VG space
- Creates filesystem and mounts the LV

### 4. LVM Extend Operations
- Extends the Logical Volume by 20% of VG space
- Resizes the filesystem to use the new space
- Verifies the extended volume and filesystem

## Prerequisites

### Required Packages
- `mdadm` - Software RAID management tool
- `lvm2` - Logical Volume Manager utilities
- Filesystem tools based on test configuration:
  - `e2fsprogs` for ext3/ext4
  - `xfsprogs` for XFS
  - `btrfs-progs` for BTRFS

### Hardware Requirements
- Minimum 2 disks for RAID1
- Minimum 3 disks for RAID5
- Minimum 4 disks for RAID6 or RAID10
- Additional spare disks (optional) for rebuild testing

## Configuration

The test uses YAML configuration files located in `swraid_lvm_extend.py.data/swraid_lvm_extend.yaml`.

### Configuration Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `disks` | Space-separated list of disks for RAID | `'sdb sdc'` |
| `spare_disks` | Space-separated list of spare disks | `'sdd'` |
| `raid` | RAID level (0, 1, 5, 6, 10, linear) | `'1'` |
| `required_disks` | Minimum disks required for RAID level | `2` |
| `raidname` | RAID device name | `'/dev/md/test_raid'` |
| `metadata` | RAID metadata version | `'1.2'` |
| `vg_name` | Volume Group name | `'test_vg'` |
| `lv_name` | Logical Volume name | `'test_lv'` |
| `fs` | Filesystem type (ext4, xfs, btrfs) | `'ext4'` |

## Usage

### Running the Test

#### Basic RAID1 with ext4:
```bash
avocado run swraid_lvm_extend.py --mux-yaml swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic
```

#### RAID5 with 3 disks and spare:
```bash
avocado run swraid_lvm_extend.py --mux-yaml swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_raid5
```

#### RAID1 with XFS filesystem:
```bash
avocado run swraid_lvm_extend.py --mux-yaml swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_xfs
```

### Custom Configuration

You can override parameters from command line:

```bash
avocado run swraid_lvm_extend.py \
    --mux-yaml swraid_lvm_extend.py.data/swraid_lvm_extend.yaml:swraid_lvm_basic \
    -p disks='sdb sdc sdd' \
    -p raid='5' \
    -p fs='xfs'
```

## Test Workflow

```
1. Setup Phase
   ├── Install required packages (mdadm, lvm2)
   ├── Validate input disks
   └── Initialize RAID and LVM parameters

2. RAID Creation & Sync
   ├── Create RAID array with specified level
   ├── Monitor initial synchronization
   └── Verify RAID status

3. RAID Rebuild (if applicable)
   ├── Remove disk from array
   ├── Add disk back to trigger rebuild
   ├── Monitor rebuild/resync progress
   └── Verify RAID integrity

4. LVM Setup
   ├── Create Physical Volume on RAID device
   ├── Create Volume Group
   ├── Create Logical Volume (50% of VG)
   ├── Create filesystem
   └── Mount filesystem

5. LVM Extend
   ├── Extend LV by 20% of VG
   ├── Resize filesystem
   └── Verify extended volume

6. Cleanup
   ├── Unmount filesystem
   ├── Remove LV and VG
   └── Stop and clean RAID array
```

## Supported RAID Levels

| RAID Level | Min Disks | Redundancy | Rebuild Test |
|------------|-----------|------------|--------------|
| RAID 0 | 2 | No | No |
| RAID 1 | 2 | Yes | Yes |
| RAID 5 | 3 | Yes | Yes |
| RAID 6 | 4 | Yes | Yes |
| RAID 10 | 4 | Yes | Yes |
| Linear | 2 | No | No |

## Expected Results

### Success Criteria
- RAID array created successfully
- Initial sync completes without errors
- Disk removal and re-addition successful (for redundant RAID levels)
- Rebuild/resync completes successfully
- LVM setup completes without errors
- Logical volume extends successfully
- Filesystem resize completes without errors
- All operations logged with detailed status

### Failure Scenarios
- RAID creation fails
- Sync timeout (default: 600 seconds)
- Rebuild timeout (default: 900 seconds)
- LVM operations fail
- Filesystem resize fails

## Troubleshooting

### Common Issues

1. **Disks not found**
   - Verify disk names are correct
   - Check disk permissions
   - Ensure disks are not in use

2. **RAID sync timeout**
   - Increase timeout in test parameters
   - Check disk performance
   - Verify no I/O errors in system logs

3. **LVM extend fails**
   - Ensure sufficient space in VG
   - Check filesystem type compatibility
   - Verify filesystem is not corrupted

4. **Permission denied errors**
   - Run test with root/sudo privileges
   - Check SELinux/AppArmor policies

## Logs and Debugging

Test logs include:
- RAID creation and status details
- Sync/rebuild progress monitoring
- LVM operation outputs
- Filesystem operations
- Detailed error messages

Check avocado test logs for complete output:
```bash
avocado run swraid_lvm_extend.py --show-job-log
```

## Author

- **Priyanka Behera** - Initial implementation (2026)

## License

This test is part of avocado-misc-tests and follows the GNU General Public License v2.0.

## References

- [mdadm man page](https://linux.die.net/man/8/mdadm)
- [LVM documentation](https://www.sourceware.org/lvm2/)
- [Avocado Framework](https://avocado-framework.github.io/)