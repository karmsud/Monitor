"""
Settings.xml writer with automatic backup creation.
"""
import xml.etree.ElementTree as ET
import os
import shutil
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("frp.xml.writer")


class XmlWriter:
    def __init__(self, settings_path: str):
        self.settings_path = os.path.abspath(settings_path)
        self.backup_dir = os.path.join(os.path.dirname(self.settings_path), "backup")

    def save(self, tree: ET.ElementTree) -> dict:
        """
        Save ElementTree to disk after creating backup.
        Steps:
        1. Create backup/ dir if not exists
        2. Copy current Settings.xml to backup/Settings_{YYYYMMDD}_{HHMMSS}.xml
        3. Write tree with xml_declaration=True, encoding='utf-8'
        4. Verify by parsing it back
        5. If write or verify fails, restore from backup
        Returns: { success: bool, backup_path: str, message: str }
        """
        backup_path: Optional[str] = None

        try:
            # Step 1: Ensure backup directory exists
            os.makedirs(self.backup_dir, exist_ok=True)
            logger.debug("Backup directory ensured: %s", self.backup_dir)

            # Step 2: Create backup of current file if it exists
            if os.path.isfile(self.settings_path):
                backup_filename = self._generate_backup_filename()
                backup_path = os.path.join(self.backup_dir, backup_filename)
                shutil.copy2(self.settings_path, backup_path)
                logger.info("Backup created: %s", backup_path)
            else:
                logger.warning(
                    "No existing Settings.xml to back up at %s; writing new file.",
                    self.settings_path,
                )

            # Step 3: Write tree to disk
            try:
                tree.write(
                    self.settings_path,
                    xml_declaration=True,
                    encoding="utf-8",
                )
                logger.info("Settings.xml written to %s", self.settings_path)
            except Exception as write_err:
                logger.error("Failed to write Settings.xml: %s", write_err)
                self._restore_from_backup(backup_path)
                return {
                    "success": False,
                    "backup_path": backup_path or "",
                    "message": f"Write failed: {write_err}. Restored from backup.",
                }

            # Step 4: Verify by parsing the written file back
            try:
                ET.parse(self.settings_path)
                logger.info("Verification passed: Settings.xml is valid XML.")
            except ET.ParseError as parse_err:
                logger.error("Verification failed – written file is not valid XML: %s", parse_err)
                self._restore_from_backup(backup_path)
                return {
                    "success": False,
                    "backup_path": backup_path or "",
                    "message": f"Verification failed: {parse_err}. Restored from backup.",
                }

            return {
                "success": True,
                "backup_path": backup_path or "",
                "message": "Settings.xml saved and verified successfully.",
            }

        except Exception as exc:
            logger.exception("Unexpected error during save: %s", exc)
            self._restore_from_backup(backup_path)
            return {
                "success": False,
                "backup_path": backup_path or "",
                "message": f"Unexpected error: {exc}",
            }

    def _generate_backup_filename(self) -> str:
        now = datetime.now()
        return f"Settings_{now.strftime('%Y%m%d_%H%M%S')}.xml"

    def _restore_from_backup(self, backup_path: Optional[str]) -> None:
        """Restore the original Settings.xml from a backup file."""
        if backup_path and os.path.isfile(backup_path):
            try:
                shutil.copy2(backup_path, self.settings_path)
                logger.info("Restored Settings.xml from backup: %s", backup_path)
            except Exception as restore_err:
                logger.critical(
                    "CRITICAL: Failed to restore from backup %s: %s",
                    backup_path,
                    restore_err,
                )
        else:
            logger.warning("No backup available to restore from.")
