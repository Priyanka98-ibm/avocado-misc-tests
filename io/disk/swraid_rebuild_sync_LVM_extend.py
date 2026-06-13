#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE for more details.
#
# Copyright: 2026 IBM
# Author: Priyanka Behera <priyankabehera@example.com>

"""
Software RAID Rebuild + Sync + LVM Extend Test
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
    """

    def setUp(self):
        self.disks = []
        self.spare_disks = []
        smm = SoftwareManager()
        detected_distro = distro.detect()

        packages = ['mdadm']
        if detected_distro.name in ['Ubuntu', 'debian']:
            packages.append('lvm2')

        for pkg in packages:
            if not smm.check_installed(pkg):
                self.log.info("Installing %s...", pkg)
                if not smm.install(pkg):
                    self.cancel("Unable to install %s" % pkg)

        disks = (self.params.get('disks', default='').strip()).split()
        if not disks:
            self.cancel('No disks provided for RAID creation')

        for dev in disks:
            self.disks.append(disk.get_absolute_disk_path(dev))

        self.raidlevel = str(self.params.get('raid', default='1'))
        required_disks = self.params.get('required_disks', default=2)

        if len(self.disks) < required_disks:
            self.cancel("Minimum %s disks required for RAID%s" %
                        (required_disks, self.raidlevel))

        spare_disks = self.params.get('spare_disks', default='')
        if spare_disks:
            for dev in spare_disks.split():
                self.spare_disks.append(disk.get_absolute_disk_path(dev))

        self.raid_name = self.params.get('raidname', default='/dev/md/test_raid')
        self.metadata = str(self.params.get('metadata', default='1.2'))

        self.vg_name = self.params.get('vg_name', default='test_vg')
        self.lv_name = self.params.get('lv_name', default='test_lv')
        self.fs_name = self.params.get('fs', default='ext4').lower()
        self.mount_loc = os.path.join(self.workdir, 'mountpoint')

        if not os.path.isdir(self.mount_loc):
            os.makedirs(self.mount_loc)

        self.rebuild_disk = None
        if self.raidlevel not in ['0', 'linear']:
            self.rebuild_disk = self.disks[-1]

        self.sraid = softwareraid.SoftwareRaid(
            self.raid_name,
            self.raidlevel,
            self.disks,
            self.metadata,
            self.spare_disks
        )

        self.log.info("RAID Configuration: Level=%s, Devices=%s, Spares=%s",
                      self.raidlevel, len(self.disks), len(self.spare_disks))

    def wait_for_sync(self, timeout=600):
        self.log.info("Waiting for RAID synchronization to complete...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                result = process.run("mdadm --detail %s" % self.raid_name,
                                     shell=True, ignore_status=True)
                output = result.stdout_text

                if ("State : clean" in output or "State : active" in output):
                    if "resync" not in output.lower() and "recovery" not in output.lower():
                        self.log.info("RAID synchronization completed successfully")
                        return True

                for line in output.split('\n'):
                    if 'resync' in line.lower() or 'recovery' in line.lower():
                        self.log.info("Sync status: %s", line.strip())

                time.sleep(5)
            except Exception as err:
                self.log.warning("Error checking sync status: %s", err)
                time.sleep(5)

        self.log.error("RAID sync did not complete within %s seconds", timeout)
        return False

    def raid_creation_and_sync(self):
        self.log.info("=" * 60)
        self.log.info("TEST 1: RAID Creation and Synchronization")
        self.log.info("=" * 60)

        if not self.sraid.create():
            self.fail("Failed to create RAID array")

        self.log.info("RAID array %s created successfully", self.raid_name)

        if not self.wait_for_sync():
            self.fail("RAID initial synchronization failed")

        result = process.run("mdadm --detail %s" % self.raid_name, shell=True)
        self.log.info("RAID Status:\n%s", result.stdout_text)

    def raid_rebuild(self):
        if not self.rebuild_disk:
            self.log.info("Skipping rebuild test (not applicable for RAID level)")
            return

        self.log.info("=" * 60)
        self.log.info("TEST 2: RAID Rebuild and Sync")
        self.log.info("=" * 60)

        self.log.info("Removing disk %s from RAID...", self.rebuild_disk)
        if not self.sraid.remove_disk(self.rebuild_disk):
            self.fail("Failed to remove disk %s" % self.rebuild_disk)

        time.sleep(2)

        self.log.info("Adding disk %s back to RAID...", self.rebuild_disk)
        if not self.sraid.add_disk(self.rebuild_disk):
            self.fail("Failed to add disk %s" % self.rebuild_disk)

        if not self.wait_for_sync(timeout=900):
            self.fail("RAID rebuild/sync failed")

        self.log.info("RAID rebuild completed successfully")

    def lvm_on_raid(self):
        self.log.info("=" * 60)
        self.log.info("TEST 3: LVM Setup on RAID")
        self.log.info("=" * 60)

        if lv_utils.vg_check(self.vg_name):
            self.log.warning("Volume group %s already exists, cleaning up...",
                             self.vg_name)
            lv_utils.vg_remove(self.vg_name)

        process.run("pvcreate -ff -y %s" % self.raid_name, shell=True)

        self.log.info("Creating Volume Group %s on %s...",
                      self.vg_name, self.raid_name)
        process.run("vgcreate %s %s" % (self.vg_name, self.raid_name), shell=True)

        if not lv_utils.vg_check(self.vg_name):
            self.fail("Volume group %s creation failed" % self.vg_name)

        vg_info = process.run("vgdisplay %s" % self.vg_name, shell=True)
        self.log.info("Volume Group Info:\n%s", vg_info.stdout_text)

        self.log.info("Creating Logical Volume %s...", self.lv_name)
        process.run("lvcreate -l 50%%VG -n %s %s" % (self.lv_name, self.vg_name),
                    shell=True)

        if not lv_utils.lv_check(self.vg_name, self.lv_name):
            self.fail("Logical volume %s creation failed" % self.lv_name)

        lv_path = "/dev/%s/%s" % (self.vg_name, self.lv_name)

        self.log.info("Creating %s filesystem...", self.fs_name)
        if self.fs_name == 'ext4':
            process.run("mkfs.ext4 -F %s" % lv_path, shell=True)
        elif self.fs_name == 'ext3':
            process.run("mkfs.ext3 -F %s" % lv_path, shell=True)
        elif self.fs_name == 'xfs':
            process.run("mkfs.xfs -f %s" % lv_path, shell=True)
        elif self.fs_name == 'btrfs':
            process.run("mkfs.btrfs -f %s" % lv_path, shell=True)
        else:
            self.fail("Unsupported filesystem type: %s" % self.fs_name)

        process.run("mount %s %s" % (lv_path, self.mount_loc), shell=True)

        result = process.run("df -h", shell=True)
        self.log.info("Mounted filesystems:\n%s", result.stdout_text)

    def lvm_extend(self):
        self.log.info("=" * 60)
        self.log.info("TEST 4: LVM Extend")
        self.log.info("=" * 60)

        lv_path = "/dev/%s/%s" % (self.vg_name, self.lv_name)

        result = process.run("lvdisplay %s" % lv_path, shell=True)
        self.log.info("Current LV Info:\n%s", result.stdout_text)

        self.log.info("Extending %s by 20%% of VG...", self.lv_name)
        try:
            process.run("lvextend -l +20%%VG %s" % lv_path, shell=True)
        except process.CmdError as err:
            self.fail("Failed to extend logical volume: %s" % err)

        self.log.info("Resizing %s filesystem...", self.fs_name)
        try:
            if self.fs_name in ['ext4', 'ext3']:
                process.run("resize2fs %s" % lv_path, shell=True)
            elif self.fs_name == 'xfs':
                process.run("xfs_growfs %s" % self.mount_loc, shell=True)
            elif self.fs_name == 'btrfs':
                process.run("btrfs filesystem resize max %s" % self.mount_loc,
                            shell=True)
        except process.CmdError as err:
            self.fail("Failed to resize filesystem: %s" % err)

        result = process.run("lvdisplay %s" % lv_path, shell=True)
        self.log.info("Extended LV Info:\n%s", result.stdout_text)

        result = process.run("df -h", shell=True)
        self.log.info("Filesystem after extend:\n%s", result.stdout_text)

        self.log.info("LVM extend completed successfully")

    def test(self):
        self.log.info("\n" + "=" * 60)
        self.log.info("Starting Software RAID + LVM Extend Test Suite")
        self.log.info("=" * 60 + "\n")

        self.raid_creation_and_sync()
        self.raid_rebuild()
        self.lvm_on_raid()
        self.lvm_extend()

        self.log.info("\n" + "=" * 60)
        self.log.info("All tests completed successfully!")
        self.log.info("=" * 60 + "\n")

    def tearDown(self):
        self.log.info("Cleaning up test environment...")

        try:
            process.run("umount %s" % self.mount_loc, shell=True, ignore_status=True)
        except Exception as err:
            self.log.warning("Error unmounting filesystem: %s", err)

        try:
            if lv_utils.lv_check(self.vg_name, self.lv_name):
                lv_utils.lv_remove(self.vg_name, self.lv_name)
        except Exception as err:
            self.log.warning("Error removing LV: %s", err)

        try:
            if lv_utils.vg_check(self.vg_name):
                lv_utils.vg_remove(self.vg_name)
        except Exception as err:
            self.log.warning("Error removing VG: %s", err)

        if hasattr(self, "sraid"):
            try:
                self.sraid.stop()
                self.sraid.clear_superblock()
            except Exception as err:
                self.log.warning("Error cleaning RAID: %s", err)

        self.log.info("Cleanup completed")

# Made with Bob
