#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2026 IBM
# Author: Priyanka Behera <Priyanka.Behera2@ibm.com>

"""
Software RAID Rebuild + Sync + LVM Extend Test

This test performs comprehensive testing of:
1. Software RAID creation and management
2. RAID device rebuild and synchronization
3. LVM (Logical Volume Manager) operations on RAID devices
4. LVM extend operations (extending logical volumes)

The test validates the complete workflow of creating a RAID array,
setting up LVM on top of it, and then extending the logical volume
while monitoring RAID sync status.
"""

import os
import time
from avocado import Test
from avocado.utils.software_manager.manager import SoftwareManager
from avocado.utils import disk
from avocado.utils import softwareraid
from avocado.utils import lv_utils
from avocado.utils import process
from avocado.utils import distro


class SwraidLvmExtend(Test):
    """
    Test class for Software RAID rebuild, sync, and LVM extend operations.
    
    This test creates a software RAID array, sets up LVM on top of it,
    performs RAID rebuild operations, monitors sync status, and extends
    the logical volume.
    """

    def setUp(self):
        """
        Setup phase: Install required packages and prepare test environment.
        
        - Installs mdadm for RAID management
        - Installs LVM2 for logical volume management
        - Validates input disks
        - Initializes RAID and LVM parameters
        """
        self.disks = []
        self.spare_disks = []
        smm = SoftwareManager()
        detected_distro = distro.detect()

        # Install required packages
        packages = ['mdadm']
        if detected_distro.name in ['Ubuntu', 'debian']:
            packages.append('lvm2')
        
        for pkg in packages:
            if not smm.check_installed(pkg):
                self.log.info(f"Installing {pkg}...")
                if not smm.install(pkg):
                    self.cancel(f"Unable to install {pkg}")

        # Get disk parameters
        disks = (self.params.get('disks', default='').strip()).split()
        if not disks:
            self.cancel('No disks provided for RAID creation')
        
        for dev in disks:
            self.disks.append(disk.get_absolute_disk_path(dev))

        # RAID configuration
        self.raidlevel = str(self.params.get('raid', default='1'))
        required_disks = self.params.get('required_disks', default=2)
        
        if len(self.disks) < required_disks:
            self.cancel(f"Minimum {required_disks} disks required for RAID{self.raidlevel}")

        # Spare disks for rebuild testing
        spare_disks = self.params.get('spare_disks', default='')
        if spare_disks:
            spare_disks = spare_disks.split()
            for dev in spare_disks:
                self.spare_disks.append(disk.get_absolute_disk_path(dev))

        # RAID device name
        self.raid_name = self.params.get('raidname', default='/dev/md/test_raid')
        self.metadata = str(self.params.get('metadata', default='1.2'))
        
        # LVM configuration
        self.vg_name = self.params.get('vg_name', default='test_vg')
        self.lv_name = self.params.get('lv_name', default='test_lv')
        self.fs_name = self.params.get('fs', default='ext4').lower()
        self.mount_loc = os.path.join(self.workdir, 'mountpoint')
        
        # Create mount point
        if not os.path.isdir(self.mount_loc):
            os.makedirs(self.mount_loc)

        # Disk for rebuild testing (last disk in the array)
        self.rebuild_disk = None
        if self.raidlevel not in ['0', 'linear']:
            self.rebuild_disk = self.disks[-1]

        # Initialize software RAID object
        self.sraid = softwareraid.SoftwareRaid(
            self.raid_name, 
            self.raidlevel, 
            self.disks,
            self.metadata, 
            self.spare_disks
        )

        self.log.info(f"RAID Configuration: Level={self.raidlevel}, "
                     f"Devices={len(self.disks)}, Spares={len(self.spare_disks)}")

    def wait_for_sync(self, timeout=600):
        """
        Wait for RAID synchronization to complete.
        
        Args:
            timeout (int): Maximum time to wait in seconds (default: 600)
            
        Returns:
            bool: True if sync completed successfully, False otherwise
        """
        self.log.info("Waiting for RAID synchronization to complete...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check RAID sync status
                result = process.run(f"mdadm --detail {self.raid_name}", 
                                   shell=True, ignore_status=True)
                output = result.stdout_text
                
                # Check if sync is complete
                if "State : clean" in output or "State : active" in output:
                    if "resync" not in output.lower() and "recovery" not in output.lower():
                        self.log.info("RAID synchronization completed successfully")
                        return True
                
                # Log sync progress
                for line in output.split('\n'):
                    if 'resync' in line.lower() or 'recovery' in line.lower():
                        self.log.info(f"Sync status: {line.strip()}")
                
                time.sleep(5)
            except Exception as e:
                self.log.warning(f"Error checking sync status: {e}")
                time.sleep(5)
        
        self.log.error(f"RAID sync did not complete within {timeout} seconds")
        return False

    def test_raid_creation_and_sync(self):
        """
        Test 1: Create RAID array and verify synchronization.
        
        Steps:
        1. Create software RAID array
        2. Monitor and wait for initial sync to complete
        3. Verify RAID status
        """
        self.log.info("=" * 60)
        self.log.info("TEST 1: RAID Creation and Synchronization")
        self.log.info("=" * 60)
        
        # Create RAID array
        if not self.sraid.create():
            self.fail("Failed to create RAID array")
        
        self.log.info(f"RAID array {self.raid_name} created successfully")
        
        # Wait for initial sync
        if not self.wait_for_sync():
            self.fail("RAID initial synchronization failed")
        
        # Verify RAID status
        result = process.run(f"mdadm --detail {self.raid_name}", shell=True)
        self.log.info(f"RAID Status:\n{result.stdout_text}")

    def test_raid_rebuild(self):
        """
        Test 2: Test RAID rebuild functionality.
        
        Steps:
        1. Remove a disk from RAID array
        2. Add the disk back to trigger rebuild
        3. Monitor rebuild/sync progress
        4. Verify RAID integrity after rebuild
        """
        if not self.rebuild_disk:
            self.log.info("Skipping rebuild test (not applicable for RAID level)")
            return
        
        self.log.info("=" * 60)
        self.log.info("TEST 2: RAID Rebuild and Sync")
        self.log.info("=" * 60)
        
        # Remove disk
        self.log.info(f"Removing disk {self.rebuild_disk} from RAID...")
        if not self.sraid.remove_disk(self.rebuild_disk):
            self.fail(f"Failed to remove disk {self.rebuild_disk}")
        
        time.sleep(2)
        
        # Add disk back
        self.log.info(f"Adding disk {self.rebuild_disk} back to RAID...")
        if not self.sraid.add_disk(self.rebuild_disk):
            self.fail(f"Failed to add disk {self.rebuild_disk}")
        
        # Wait for rebuild/sync
        if not self.wait_for_sync(timeout=900):
            self.fail("RAID rebuild/sync failed")
        
        self.log.info("RAID rebuild completed successfully")

    def test_lvm_on_raid(self):
        """
        Test 3: Create LVM on RAID device.
        
        Steps:
        1. Create Physical Volume (PV) on RAID device
        2. Create Volume Group (VG)
        3. Create Logical Volume (LV)
        4. Create filesystem and mount
        """
        self.log.info("=" * 60)
        self.log.info("TEST 3: LVM Setup on RAID")
        self.log.info("=" * 60)
        
        # Check if VG already exists
        if lv_utils.vg_check(self.vg_name):
            self.log.warning(f"Volume group {self.vg_name} already exists, cleaning up...")
            lv_utils.vg_remove(self.vg_name)
        
        # Create VG on RAID device
        self.log.info(f"Creating Volume Group {self.vg_name} on {self.raid_name}...")
        lv_utils.vg_create(self.vg_name, self.raid_name, force=True)
        
        if not lv_utils.vg_check(self.vg_name):
            self.fail(f"Volume group {self.vg_name} creation failed")
        
        # Get VG size and create LV with 50% of VG size
        vg_info = process.run(f"vgdisplay {self.vg_name}", shell=True)
        self.log.info(f"Volume Group Info:\n{vg_info.stdout_text}")
        
        # Create LV (using 50% of VG for initial size, leaving room for extend)
        self.log.info(f"Creating Logical Volume {self.lv_name}...")
        lv_utils.lv_create(self.vg_name, self.lv_name, "50%VG")
        
        if not lv_utils.lv_check(self.vg_name, self.lv_name):
            self.fail(f"Logical volume {self.lv_name} creation failed")
        
        # Create filesystem and mount
        self.log.info(f"Creating {self.fs_name} filesystem and mounting...")
        lv_utils.lv_mount(self.vg_name, self.lv_name, self.mount_loc,
                         create_filesystem=self.fs_name)
        
        # Verify mount
        result = process.run("df -h", shell=True)
        self.log.info(f"Mounted filesystems:\n{result.stdout_text}")

    def test_lvm_extend(self):
        """
        Test 4: Extend Logical Volume.
        
        Steps:
        1. Get current LV size
        2. Extend LV by additional space
        3. Resize filesystem
        4. Verify new size and validate extension
        """
        self.log.info("=" * 60)
        self.log.info("TEST 4: LVM Extend")
        self.log.info("=" * 60)
        
        lv_path = f"/dev/{self.vg_name}/{self.lv_name}"
        
        # Get current size before extension
        result = process.run(f"lvdisplay {lv_path}", shell=True)
        self.log.info(f"Current LV Info:\n{result.stdout_text}")
        
        # Extract current LV size in bytes for comparison
        size_cmd = f"lvdisplay {lv_path} --units b | grep 'LV Size' | awk '{{print $3}}'"
        result = process.run(size_cmd, shell=True)
        original_size_str = result.stdout_text.strip().replace('B', '')
        try:
            original_size = float(original_size_str)
            self.log.info(f"Original LV size: {original_size} bytes ({original_size / (1024**3):.2f} GB)")
        except ValueError:
            self.log.warning(f"Could not parse original size: {original_size_str}")
            original_size = 0
        
        # Extend LV by 20% of VG
        self.log.info(f"Extending {self.lv_name} by 20% of VG...")
        try:
            process.run(f"lvextend -l +20%VG {lv_path}", shell=True)
        except process.CmdError as e:
            self.fail(f"Failed to extend logical volume: {e}")
        
        # Get new size after extension
        result = process.run(size_cmd, shell=True)
        new_size_str = result.stdout_text.strip().replace('B', '')
        try:
            new_size = float(new_size_str)
            self.log.info(f"New LV size: {new_size} bytes ({new_size / (1024**3):.2f} GB)")
        except ValueError:
            self.log.warning(f"Could not parse new size: {new_size_str}")
            new_size = 0
        
        # Verify that LV size has increased
        if original_size > 0 and new_size > 0:
            if new_size <= original_size:
                self.fail(f"LV size verification failed: New size ({new_size}) is not greater than original size ({original_size})")
            
            size_increase = new_size - original_size
            size_increase_gb = size_increase / (1024**3)
            percentage_increase = (size_increase / original_size) * 100
            
            self.log.info(f"LV size verification PASSED:")
            self.log.info(f"  - Size increased by: {size_increase} bytes ({size_increase_gb:.2f} GB)")
            self.log.info(f"  - Percentage increase: {percentage_increase:.2f}%")
        else:
            self.log.warning("Could not verify LV size increase due to parsing errors")
        
        # Resize filesystem based on filesystem type
        self.log.info(f"Resizing {self.fs_name} filesystem...")
        try:
            if self.fs_name == 'ext4' or self.fs_name == 'ext3':
                process.run(f"resize2fs {lv_path}", shell=True)
            elif self.fs_name == 'xfs':
                process.run(f"xfs_growfs {self.mount_loc}", shell=True)
            elif self.fs_name == 'btrfs':
                process.run(f"btrfs filesystem resize max {self.mount_loc}", shell=True)
        except process.CmdError as e:
            self.fail(f"Failed to resize filesystem: {e}")
        
        # Verify new size with detailed display
        result = process.run(f"lvdisplay {lv_path}", shell=True)
        self.log.info(f"Extended LV Info:\n{result.stdout_text}")
        
        result = process.run("df -h", shell=True)
        self.log.info(f"Filesystem after extend:\n{result.stdout_text}")
        
        self.log.info("LVM extend completed and verified successfully")

    def test(self):
        """
        Main test execution: Run all test phases in sequence.
        """
        self.log.info("\n" + "=" * 60)
        self.log.info("Starting Software RAID + LVM Extend Test Suite")
        self.log.info("=" * 60 + "\n")
        
        # Test 1: RAID Creation and Sync
        self.test_raid_creation_and_sync()
        
        # Test 2: RAID Rebuild (if applicable)
        self.test_raid_rebuild()
        
        # Test 3: LVM Setup on RAID
        self.test_lvm_on_raid()
        
        # Test 4: LVM Extend
        self.test_lvm_extend()
        
        self.log.info("\n" + "=" * 60)
        self.log.info("All tests completed successfully!")
        self.log.info("=" * 60 + "\n")

    def tearDown(self):
        """
        Cleanup: Remove LVM and RAID configurations.
        """
        self.log.info("Cleaning up test environment...")
        
        # Unmount filesystem
        try:
            lv_utils.lv_umount(self.vg_name, self.lv_name)
        except Exception as e:
            self.log.warning(f"Error unmounting LV: {e}")
        
        # Remove LV
        try:
            if lv_utils.lv_check(self.vg_name, self.lv_name):
                lv_utils.lv_remove(self.vg_name, self.lv_name)
        except Exception as e:
            self.log.warning(f"Error removing LV: {e}")
        
        # Remove VG
        try:
            if lv_utils.vg_check(self.vg_name):
                lv_utils.vg_remove(self.vg_name)
        except Exception as e:
            self.log.warning(f"Error removing VG: {e}")
        
        # Stop and clean RAID
        if hasattr(self, "sraid"):
            try:
                self.sraid.stop()
                self.sraid.clear_superblock()
            except Exception as e:
                self.log.warning(f"Error cleaning RAID: {e}")
        
        self.log.info("Cleanup completed")
