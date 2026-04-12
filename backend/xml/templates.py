"""Template inventory — discover reusable job patterns from Settings.xml."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

from .models import EmailJob, JobTemplate, SftpJob
from .parser import SettingsXmlParser

logger = logging.getLogger("frp.xml.templates")


class TemplateInventory:
    """Discover and catalogue reusable job configuration patterns.

    Parameters
    ----------
    settings_path : str
        Filesystem path to the Settings.xml file.
    xml_type : str
        Either ``'email'`` or ``'sftp'``.
    """

    def __init__(self, settings_path: str, xml_type: str = "email") -> None:
        self.settings_path = settings_path
        self.xml_type = xml_type

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def discover_templates(
        self, filter_query: Optional[str] = None
    ) -> List[JobTemplate]:
        """Analyse all jobs and group them into template patterns.

        Parameters
        ----------
        filter_query : str, optional
            If provided, only templates whose pattern name contains this
            substring (case-insensitive) are returned.

        Returns
        -------
        list[JobTemplate]
            One entry per unique parser+template combination found.
        """
        parser = SettingsXmlParser(self.settings_path)
        jobs = parser.get_all_jobs()

        # Group by signature (parser+template combo)
        groups: Dict[str, List[Union[EmailJob, SftpJob]]] = defaultdict(list)
        for job in jobs:
            sig = self._compute_signature(job)
            groups[sig].append(job)

        templates: List[JobTemplate] = []
        for sig, group in groups.items():
            first = group[0]
            parser_names = sorted(first.parsers.keys()) if first.parsers else []
            template_names = sorted(first.templates.keys()) if first.templates else []
            pattern_name = self._compute_pattern_name(parser_names, template_names)

            has_servicer = False
            if isinstance(first, EmailJob):
                has_servicer = first.servicer_id is not None
            elif isinstance(first, SftpJob):
                has_servicer = first.servicer_id != 0

            mailbox_pattern = ""
            if isinstance(first, EmailJob):
                mailbox_pattern = first.mailbox or ""

            template = JobTemplate(
                pattern_name=pattern_name,
                parser_names=parser_names,
                template_names=template_names,
                mailbox_pattern=mailbox_pattern,
                example_job_name=first.name,
                job_count=len(group),
                has_servicer_id=has_servicer,
                sample_fields=self._extract_sample_fields(first),
            )
            templates.append(template)

        # Apply filter
        if filter_query:
            q = filter_query.lower()
            templates = [
                t for t in templates
                if q in t.pattern_name.lower()
                or any(q in p.lower() for p in t.parser_names)
                or any(q in t_name.lower() for t_name in t.template_names)
            ]

        # Sort by job_count descending
        templates.sort(key=lambda t: t.job_count, reverse=True)
        return templates

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _compute_signature(self, job: Union[EmailJob, SftpJob]) -> str:
        """Hash the parser+template combination to group similar jobs."""
        parser_names = sorted(job.parsers.keys()) if job.parsers else []
        template_names = sorted(job.templates.keys()) if job.templates else []
        raw = "|".join(parser_names) + "||" + "|".join(template_names)
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _compute_pattern_name(
        parsers: List[str], templates: List[str]
    ) -> str:
        """Build a human-readable pattern name from parser/template lists."""
        parts: List[str] = []
        if parsers:
            parts.append("+".join(parsers))
        if templates:
            parts.append("[" + "+".join(templates) + "]")
        return " ".join(parts) if parts else "(empty)"

    @staticmethod
    def _extract_sample_fields(job: Union[EmailJob, SftpJob]) -> Dict[str, Any]:
        """Extract a representative sample of fields from a job."""
        sample: Dict[str, Any] = {"name": job.name, "xml_type": job.xml_type}

        if isinstance(job, EmailJob):
            sample["mailbox"] = job.mailbox
            sample["folder"] = job.folder
            sample["sme"] = job.sme
            sample["save_location"] = job.save_location
            sample["servicer_id"] = job.servicer_id
        elif isinstance(job, SftpJob):
            sample["path"] = job.path
            sample["dsn"] = job.dsn
            sample["sme"] = job.sme
            sample["save_location"] = job.save_location
            sample["servicer_id"] = job.servicer_id

        return sample
