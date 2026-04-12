"""Rollback handler — safely restore a Settings.xml backup."""

from __future__ import annotations

import logging
import shutil
from typing import Dict

from .diff import XmlDiffEngine
from .models import DiffResult
from .parser import SettingsXmlParser
from .writer import XmlWriter

logger = logging.getLogger("frp.xml.rollback")


class RollbackHandler:
    """Preview and execute a rollback of Settings.xml to a prior backup.

    Parameters
    ----------
    settings_path : str
        Path to the current (active) Settings.xml.
    xml_type : str
        Either ``'email'`` or ``'sftp'``.
    """

    def __init__(self, settings_path: str, xml_type: str = "email") -> None:
        self.settings_path = settings_path
        self.xml_type = xml_type

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def preview(self, backup_file: str) -> DiffResult:
        """Return a diff showing what *would* change if we rolled back.

        Parameters
        ----------
        backup_file : str
            Path to the backup file to compare against.

        Returns
        -------
        DiffResult
        """
        engine = XmlDiffEngine(self.xml_type)
        return engine.diff(self.settings_path, backup_file)

    def execute(self, backup_file: str) -> Dict:
        """Perform a rollback: backup current state, then overwrite with *backup_file*.

        Steps:
            1. Save current Settings.xml (creates a safety backup).
            2. Copy *backup_file* over the active Settings.xml.
            3. Validate the restored file.
            4. Return result dict.

        Returns
        -------
        dict
            Keys: ``safety_backup``, ``restored_from``, ``validation``.
        """
        # Step 1: Create safety backup of current state
        parser = SettingsXmlParser(self.settings_path)
        tree = parser.get_element_tree()
        writer = XmlWriter(self.settings_path)
        save_result = writer.save(tree)

        safety_backup = save_result.get("backup_path", "")
        logger.info("Safety backup created: %s", safety_backup)

        # Step 2: Overwrite active file with the selected backup
        shutil.copy2(backup_file, self.settings_path)
        logger.info("Restored %s from %s", self.settings_path, backup_file)

        # Step 3: Validate the restored file
        restored_parser = SettingsXmlParser(self.settings_path)
        validation = restored_parser.validate()

        return {
            "safety_backup": safety_backup,
            "restored_from": backup_file,
            "validation": validation.to_dict(),
        }
