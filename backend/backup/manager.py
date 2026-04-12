"""Backup file management for Settings.xml files."""
import os
import re
import shutil
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("frp.backup")


class BackupManager:
    FILENAME_PATTERN = re.compile(r'^Settings_(\d{8})_(\d{6})\.xml$')

    def __init__(self, settings_path: str):
        self.settings_path = os.path.abspath(settings_path)
        self.backup_dir = os.path.join(os.path.dirname(self.settings_path), "backup")

    def list_backups(self) -> List[dict]:
        """List all backup files sorted newest first.

        Returns a list of dicts, each containing:
            filename     – backup file name
            full_path    – absolute path to the backup file
            timestamp    – datetime when the backup was created (parsed from filename)
            size_bytes   – file size in bytes
            age_days     – number of days since the backup was created
        """
        if not os.path.isdir(self.backup_dir):
            logger.debug("Backup directory does not exist: %s", self.backup_dir)
            return []

        backups: List[dict] = []
        now = datetime.now()

        for entry in os.listdir(self.backup_dir):
            match = self.FILENAME_PATTERN.match(entry)
            if not match:
                continue

            date_part, time_part = match.group(1), match.group(2)
            try:
                timestamp = datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
            except ValueError:
                logger.warning("Skipping file with unparseable timestamp: %s", entry)
                continue

            full_path = os.path.join(self.backup_dir, entry)
            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                size_bytes = 0

            age_delta = now - timestamp
            age_days = age_delta.days

            backups.append({
                "filename": entry,
                "full_path": full_path,
                "timestamp": timestamp,
                "size_bytes": size_bytes,
                "age_days": age_days,
            })

        backups.sort(key=lambda b: b["timestamp"], reverse=True)
        logger.debug("Found %d backup(s) in %s", len(backups), self.backup_dir)
        return backups

    def restore(self, backup_filename: str) -> dict:
        """Restore a backup file over the current Settings.xml.

        Steps:
            1. Validate the requested backup exists and is valid XML.
            2. Create a safety backup of the current Settings.xml (pre-restore snapshot).
            3. Copy the requested backup over the current Settings.xml.
            4. Verify the restored file is valid XML.

        Returns:
            { success: bool, safety_backup: str, message: str }
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)

        # --- Validate requested backup exists ---
        if not os.path.isfile(backup_path):
            msg = f"Backup file not found: {backup_path}"
            logger.error(msg)
            return {"success": False, "safety_backup": "", "message": msg}

        # --- Validate requested backup is well-formed XML ---
        try:
            ET.parse(backup_path)
        except ET.ParseError as err:
            msg = f"Backup file is not valid XML: {err}"
            logger.error(msg)
            return {"success": False, "safety_backup": "", "message": msg}

        # --- Step 1: Safety backup of current file ---
        safety_backup = ""
        if os.path.isfile(self.settings_path):
            os.makedirs(self.backup_dir, exist_ok=True)
            safety_name = f"Settings_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            safety_backup = os.path.join(self.backup_dir, safety_name)
            try:
                shutil.copy2(self.settings_path, safety_backup)
                logger.info("Safety backup created: %s", safety_backup)
            except OSError as err:
                msg = f"Failed to create safety backup: {err}"
                logger.error(msg)
                return {"success": False, "safety_backup": "", "message": msg}

        # --- Step 2: Copy backup over current ---
        try:
            shutil.copy2(backup_path, self.settings_path)
            logger.info("Restored %s → %s", backup_filename, self.settings_path)
        except OSError as err:
            msg = f"Failed to copy backup over Settings.xml: {err}"
            logger.error(msg)
            # Attempt to roll back using safety backup
            if safety_backup and os.path.isfile(safety_backup):
                try:
                    shutil.copy2(safety_backup, self.settings_path)
                    logger.info("Rolled back to safety backup after failed restore.")
                except OSError:
                    logger.critical("CRITICAL: Rollback also failed.")
            return {"success": False, "safety_backup": safety_backup, "message": msg}

        # --- Step 3: Verify restored file ---
        try:
            ET.parse(self.settings_path)
        except ET.ParseError as err:
            msg = f"Restored file failed XML verification: {err}"
            logger.error(msg)
            # Roll back
            if safety_backup and os.path.isfile(safety_backup):
                try:
                    shutil.copy2(safety_backup, self.settings_path)
                    logger.info("Rolled back to safety backup after verification failure.")
                except OSError:
                    logger.critical("CRITICAL: Rollback also failed after verification failure.")
            return {"success": False, "safety_backup": safety_backup, "message": msg}

        return {
            "success": True,
            "safety_backup": safety_backup,
            "message": f"Successfully restored {backup_filename}.",
        }

    def get_backup_count(self) -> int:
        """Return the number of available backup files."""
        return len(self.list_backups())

    def get_latest_backup(self) -> Optional[dict]:
        """Return the most recent backup entry, or None if no backups exist."""
        backups = self.list_backups()
        if backups:
            return backups[0]
        return None
