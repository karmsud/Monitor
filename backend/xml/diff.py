"""XML diff engine — compare two Settings.xml files and report changes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

from .models import DiffResult, FieldChange, JobDiff, EmailJob, SftpJob
from .parser import SettingsXmlParser

logger = logging.getLogger("frp.xml.diff")

# Fields to compare per job type
_EMAIL_COMPARE_FIELDS = ("name", "servicer_id", "mailbox", "folder", "sme", "save_location")
_SFTP_COMPARE_FIELDS = ("name", "servicer_id", "path", "dsn", "sme", "save_location")


class XmlDiffEngine:
    """Compare two Settings.xml files and produce a structured diff.

    Parameters
    ----------
    xml_type : str
        Either ``'email'`` or ``'sftp'``.
    """

    def __init__(self, xml_type: str = "email") -> None:
        self.xml_type = xml_type

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def diff(self, current_path: str, backup_path: str) -> DiffResult:
        """Compare *current_path* against *backup_path* and return changes.

        Parameters
        ----------
        current_path : str
            Path to the current (active) Settings.xml.
        backup_path : str
            Path to the backup Settings.xml to compare against.

        Returns
        -------
        DiffResult
        """
        current_parser = SettingsXmlParser(current_path)
        backup_parser = SettingsXmlParser(backup_path)

        current_jobs = current_parser.get_all_jobs()
        backup_jobs = backup_parser.get_all_jobs()

        current_map: Dict[str, Union[EmailJob, SftpJob]] = {
            j.name: j for j in current_jobs
        }
        backup_map: Dict[str, Union[EmailJob, SftpJob]] = {
            j.name: j for j in backup_jobs
        }

        result = DiffResult(
            current_file=current_path,
            backup_file=backup_path,
            timestamp=datetime.now().isoformat(),
        )

        # Detect added jobs (in current but not in backup)
        for name in current_map:
            if name not in backup_map:
                result.added_jobs.append(JobDiff(
                    job_name=name,
                    change_type="added",
                ))

        # Detect removed jobs (in backup but not in current)
        for name in backup_map:
            if name not in current_map:
                result.removed_jobs.append(JobDiff(
                    job_name=name,
                    change_type="removed",
                ))

        # Detect modified jobs
        for name in current_map:
            if name in backup_map:
                changes = self._compare_jobs(current_map[name], backup_map[name])
                if changes:
                    result.modified_jobs.append(JobDiff(
                        job_name=name,
                        change_type="modified",
                        field_changes=changes,
                    ))
                else:
                    result.unchanged_count += 1

        logger.info(
            "Diff complete: +%d / -%d / ~%d / =%d",
            len(result.added_jobs),
            len(result.removed_jobs),
            len(result.modified_jobs),
            result.unchanged_count,
        )
        return result

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _compare_jobs(
        self,
        current_job: Union[EmailJob, SftpJob],
        backup_job: Union[EmailJob, SftpJob],
    ) -> List[FieldChange]:
        """Compare two job instances and return a list of field-level changes."""
        changes: List[FieldChange] = []

        # Pick comparison fields based on type
        if isinstance(current_job, EmailJob):
            compare_fields = _EMAIL_COMPARE_FIELDS
        else:
            compare_fields = _SFTP_COMPARE_FIELDS

        # Compare scalar fields
        for field_name in compare_fields:
            old_val = str(getattr(backup_job, field_name, "") or "")
            new_val = str(getattr(current_job, field_name, "") or "")
            if old_val != new_val:
                changes.append(FieldChange(
                    field=field_name,
                    old_value=old_val,
                    new_value=new_val,
                ))

        # Compare parsers (dict keys)
        old_parsers = sorted(backup_job.parsers.keys()) if backup_job.parsers else []
        new_parsers = sorted(current_job.parsers.keys()) if current_job.parsers else []
        if old_parsers != new_parsers:
            changes.append(FieldChange(
                field="parsers",
                old_value=", ".join(old_parsers),
                new_value=", ".join(new_parsers),
            ))

        # Compare templates (dict keys)
        old_templates = sorted(backup_job.templates.keys()) if backup_job.templates else []
        new_templates = sorted(current_job.templates.keys()) if current_job.templates else []
        if old_templates != new_templates:
            changes.append(FieldChange(
                field="templates",
                old_value=", ".join(old_templates),
                new_value=", ".join(new_templates),
            ))

        return changes
