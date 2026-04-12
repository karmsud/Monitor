"""Settings.xml parser for email and SFTP monitoring configurations."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Union

from .models import EmailJob, SftpJob, ValidationResult

logger = logging.getLogger("frp.xml.parser")


class SettingsXmlParser:
    """Parse, query, and validate a Settings.xml file.

    Supports two flavours:
    * **email** – contains ``<MailboxCollection>`` with ``<JOB_NAME>`` children
    * **sftp**  – contains ``<FolderCollection>`` with ``<JOB_NAME>`` children
    """

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def __init__(self, path: str) -> None:
        """Read and parse the XML file at *path*.

        Args:
            path: Filesystem path to a Settings.xml file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ET.ParseError: If the file is not well-formed XML.
        """
        self.path = path
        logger.debug("Parsing XML file: %s", path)
        self.tree: ET.ElementTree = ET.parse(path)
        self.root: ET.Element = self.tree.getroot()

    # ------------------------------------------------------------------ #
    #  Public helpers
    # ------------------------------------------------------------------ #

    def _find_collection(self, tag: str) -> Optional[ET.Element]:
        """Locate a collection element by *tag* in two possible locations.

        Production SFTP Settings.xml places ``<FolderCollection>`` directly
        under ``<Settings>`` (the root), while the email Settings.xml wraps
        it inside ``<Outlook>``.  This helper checks both.
        """
        # Preferred: under <Outlook>
        outlook = self.root.find("Outlook")
        if outlook is not None:
            el = outlook.find(tag)
            if el is not None:
                return el
        # Fallback: directly under root
        return self.root.find(tag)

    def detect_xml_type(self) -> str:
        """Return ``'email'``, ``'sftp'``, or ``'unknown'``.

        Detection checks for ``<MailboxCollection>`` or
        ``<FolderCollection>`` under ``<Outlook>`` first, then directly
        under the document root (production SFTP layout).
        """
        if self._find_collection("MailboxCollection") is not None:
            return "email"
        if self._find_collection("FolderCollection") is not None:
            return "sftp"
        return "unknown"

    def get_all_jobs(self) -> List[Union[EmailJob, SftpJob]]:
        """Parse and return every job defined in the XML."""
        xml_type = self.detect_xml_type()
        jobs: List[Union[EmailJob, SftpJob]] = []

        if xml_type == "email":
            collection = self._find_collection("MailboxCollection")
            if collection is not None:
                for child in collection:
                    jobs.append(self._parse_email_job(child, child.tag))
        elif xml_type == "sftp":
            collection = self._find_collection("FolderCollection")
            if collection is not None:
                for child in collection:
                    jobs.append(self._parse_sftp_job(child, child.tag))
        else:
            logger.warning("Unknown XML type – no jobs parsed from %s", self.path)

        logger.debug("Parsed %d job(s) from %s", len(jobs), self.path)
        return jobs

    def search_jobs(self, query: str) -> List[Union[EmailJob, SftpJob]]:
        """Return jobs matching a free-text *query* (case-insensitive).

        Special keywords:
        * ``shelf-level`` / ``no servicerid`` – jobs where ServicerID is
          absent (``None`` for email, ``0`` for sftp).
        * ``email`` / ``sftp`` – filter by job type.

        Natural-language intent phrases like "list all email jobs",
        "show me all sftp jobs", "get all jobs" are recognised and
        return the appropriate unfiltered set.
        """
        all_jobs = self.get_all_jobs()
        q = query.strip().lower()
        words = set(q.split())

        # --- special keyword filters ---------------------------------- #
        if q in ("shelf-level", "no servicerid"):
            return [
                j for j in all_jobs
                if (isinstance(j, EmailJob) and j.servicer_id is None)
                or (isinstance(j, SftpJob) and j.servicer_id == 0)
            ]

        # Intent: user wants all email jobs ("list all email jobs",
        # "show email jobs", "email", etc.)
        if "email" in words and "sftp" not in words:
            return [j for j in all_jobs if isinstance(j, EmailJob)]

        # Intent: user wants all SFTP jobs
        if "sftp" in words and "email" not in words:
            return [j for j in all_jobs if isinstance(j, SftpJob)]

        # Intent: user wants everything ("list all jobs", "show all",
        # "all jobs", etc.) — detect when the only meaningful words are
        # generic intent words.
        _INTENT_WORDS = {"list", "show", "find", "get", "search", "display",
                         "all", "every", "jobs", "job", "email", "sftp",
                         "me", "the", "my", "give", "check", "look"}
        if words and words <= _INTENT_WORDS:
            return all_jobs

        # --- generic free-text search --------------------------------- #
        return [j for j in all_jobs if j.matches_query(q)]

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #

    def validate(
        self, db_servicer_ids: Optional[set] = None
    ) -> ValidationResult:
        """Run a full validation pass over the parsed XML.

        Errors (E001–E013), Warnings (W001–W005) and Info (I001–I006)
        are appended to the returned :class:`ValidationResult`.

        Args:
            db_servicer_ids: Optional set of valid servicer-id integers
                known to the database.  When supplied, a warning is raised
                for any XML servicer-id that is not in this set.
        """
        result = ValidationResult()
        xml_type = self.detect_xml_type()
        result.xml_type = xml_type

        # E001 is raised at parse time (__init__), not here.

        # E003 – Missing <MailboxCollection> / <FolderCollection>
        if xml_type == "unknown":
            result.add_error(
                "E003: Missing <MailboxCollection> or <FolderCollection> "
                "under <Outlook> or document root"
            )
            return result

        # Determine collection (checks <Outlook>/X then root/X)
        if xml_type == "email":
            collection = self._find_collection("MailboxCollection")
        else:
            collection = self._find_collection("FolderCollection")

        if collection is None:
            result.add_error(
                "E003: Missing <MailboxCollection> or <FolderCollection> "
                "under <Outlook> or document root"
            )
            return result

        job_names: List[str] = []
        servicer_ids_found: List[Optional[int]] = []
        mailboxes_or_paths: List[str] = []
        templates_in_use: List[str] = []

        for child in collection:
            name = child.tag
            job_names.append(name)

            if xml_type == "email":
                self._validate_email_job(child, name, result, db_servicer_ids)
                # Collect stats
                sid = self._text(child, "ServicerID")
                servicer_ids_found.append(
                    self._parse_int(sid) if sid else None
                )
                mb = self._text(child, "Mailbox")
                if mb:
                    mailboxes_or_paths.append(mb)
            else:
                self._validate_sftp_job(child, name, result, db_servicer_ids)
                sid = self._text(child, "ServicerID")
                servicer_ids_found.append(
                    self._parse_int(sid) if sid else None
                )
                p = self._text(child, "Path")
                if p:
                    mailboxes_or_paths.append(p)

            # Collect templates
            tpl_el = child.find("Templates")
            if tpl_el is not None:
                for t in tpl_el:
                    if t.text:
                        templates_in_use.append(t.text)

        # E008 – Duplicate job names
        seen: Dict[str, int] = {}
        for n in job_names:
            seen[n] = seen.get(n, 0) + 1
        for n, count in seen.items():
            if count > 1:
                result.add_error(
                    f"E008: Duplicate job name '{n}' appears {count} times"
                )

        result.job_count = len(job_names)

        # ---- Info codes ---------------------------------------------- #
        result.add_info(f"I001: Total jobs found: {len(job_names)}")

        with_sid = sum(1 for s in servicer_ids_found if s is not None)
        without_sid = len(servicer_ids_found) - with_sid
        result.add_info(f"I002: Jobs with ServicerID: {with_sid}")
        result.add_info(
            f"I003: Jobs without ServicerID (shelf-level): {without_sid}"
        )

        unique_sids = {s for s in servicer_ids_found if s is not None}
        result.add_info(f"I004: Unique ServicerIDs: {len(unique_sids)}")

        unique_mp = set(mailboxes_or_paths)
        label = "mailboxes" if xml_type == "email" else "paths"
        result.add_info(f"I005: Unique {label}: {len(unique_mp)}")

        unique_tpls = sorted(set(templates_in_use))
        result.add_info(f"I006: Templates in use: {unique_tpls}")

        return result

    # ------------------------------------------------------------------ #
    #  Private – email job validation
    # ------------------------------------------------------------------ #

    def _validate_email_job(
        self,
        element: ET.Element,
        name: str,
        result: ValidationResult,
        db_servicer_ids: Optional[set],
    ) -> None:
        """Validate a single email job element."""
        # E004 – missing <Mailbox>
        if not self._text(element, "Mailbox"):
            result.add_error(f"E004: Job '{name}' missing required <Mailbox>")

        # E005 – missing <SME>
        if not self._text(element, "SME"):
            result.add_error(f"E005: Job '{name}' missing required <SME>")

        # E006 – missing <Parsers>
        if element.find("Parsers") is None:
            result.add_error(f"E006: Job '{name}' missing <Parsers> element")

        # E007 – missing <SaveLocation>
        if not self._text(element, "SaveLocation"):
            result.add_error(f"E007: Job '{name}' missing <SaveLocation>")

        # W001 – ServicerID not in database
        sid_text = self._text(element, "ServicerID")
        if sid_text and db_servicer_ids is not None:
            sid_int = self._parse_int(sid_text)
            if sid_int is not None and sid_int not in db_servicer_ids:
                result.add_warning(
                    f"W001: Job '{name}' ServicerID {sid_int} not found "
                    "in database"
                )

        # W002 – empty <Filters>
        filters_el = element.find("Filters")
        if filters_el is not None and len(filters_el) == 0:
            result.add_warning(
                f"W002: Job '{name}' has empty <Filters> block"
            )

        # W003 – SaveLocation without tokens
        save_loc = self._text(element, "SaveLocation") or ""
        if save_loc and not re.search(r"\{.+?\}", save_loc):
            result.add_warning(
                f"W003: Job '{name}' SaveLocation contains no tokens"
            )

        # W004 – unparseable <LastEmail>
        last_email = self._text(element, "LastEmail")
        if last_email:
            if not self._looks_like_timestamp(last_email):
                result.add_warning(
                    f"W004: Job '{name}' <LastEmail> timestamp unparseable: "
                    f"'{last_email}'"
                )

        # W005 – invalid <DayAdjust>
        da_text = self._text(element, "DayAdjust")
        if da_text and self._parse_int(da_text) is None:
            result.add_warning(
                f"W005: Job '{name}' <DayAdjust> '{da_text}' is not a "
                "valid integer"
            )

    # ------------------------------------------------------------------ #
    #  Private – sftp job validation
    # ------------------------------------------------------------------ #

    def _validate_sftp_job(
        self,
        element: ET.Element,
        name: str,
        result: ValidationResult,
        db_servicer_ids: Optional[set],
    ) -> None:
        """Validate a single SFTP job element."""
        # E004 – missing <Path>
        if not self._text(element, "Path"):
            result.add_error(f"E004: Job '{name}' missing required <Path>")

        # E005 – missing <SME>
        if not self._text(element, "SME"):
            result.add_error(f"E005: Job '{name}' missing required <SME>")

        # E006 – missing <Parsers>
        if element.find("Parsers") is None:
            result.add_error(f"E006: Job '{name}' missing <Parsers> element")

        # E007 – missing <SaveLocation>
        if not self._text(element, "SaveLocation"):
            result.add_error(f"E007: Job '{name}' missing <SaveLocation>")

        # E009 – missing <ServicerID>
        if not self._text(element, "ServicerID"):
            result.add_error(f"E009: Job '{name}' missing <ServicerID>")

        # E010 – missing <DSN>
        if not self._text(element, "DSN"):
            result.add_error(f"E010: Job '{name}' missing <DSN>")

        # E011 – missing <SkipList>
        if not self._text(element, "SkipList"):
            result.add_error(f"E011: Job '{name}' missing <SkipList>")

        # E012 – missing <IgnoreList>
        if not self._text(element, "IgnoreList"):
            result.add_error(f"E012: Job '{name}' missing <IgnoreList>")

        # E013 – missing <ZipContentFilter>
        if not self._text(element, "ZipContentFilter"):
            result.add_error(
                f"E013: Job '{name}' missing <ZipContentFilter>"
            )

        # W001 – ServicerID not in database
        sid_text = self._text(element, "ServicerID")
        if sid_text and db_servicer_ids is not None:
            sid_int = self._parse_int(sid_text)
            if sid_int is not None and sid_int not in db_servicer_ids:
                result.add_warning(
                    f"W001: Job '{name}' ServicerID {sid_int} not found "
                    "in database"
                )

        # W003 – SaveLocation without tokens
        save_loc = self._text(element, "SaveLocation") or ""
        if save_loc and not re.search(r"\{.+?\}", save_loc):
            result.add_warning(
                f"W003: Job '{name}' SaveLocation contains no tokens"
            )

        # W005 – invalid <DayAdjust>
        da_text = self._text(element, "DayAdjust")
        if da_text and self._parse_int(da_text) is None:
            result.add_warning(
                f"W005: Job '{name}' <DayAdjust> '{da_text}' is not a "
                "valid integer"
            )

    # ------------------------------------------------------------------ #
    #  Job parsing
    # ------------------------------------------------------------------ #

    def _parse_email_job(self, element: ET.Element, name: str) -> EmailJob:
        """Parse a single ``<JOB_NAME>`` element into an :class:`EmailJob`.

        Args:
            element: The XML element representing the job.
            name: The tag name (used as the job name).
        """
        sid_text = self._text(element, "ServicerID")
        da_text = self._text(element, "DayAdjust")
        qof_text = self._text(element, "QueueOneFile")

        return EmailJob(
            name=name,
            mailbox=self._text(element, "Mailbox") or "",
            folder=self._text(element, "Folder") or "",
            sme=self._text(element, "SME") or "",
            last_email=self._text(element, "LastEmail"),
            save_location=self._text(element, "SaveLocation") or "",
            filters=self._child_dict(element, "Filters"),
            parsers=self._child_dict(element, "Parsers"),
            servicer_id=self._parse_int(sid_text) if sid_text else None,
            queue_one_file=self._parse_bool(qof_text) if qof_text else None,
            templates=self._child_dict(element, "Templates"),
            day_adjust=self._parse_int(da_text) if da_text else None,
        )

    def _parse_sftp_job(self, element: ET.Element, name: str) -> SftpJob:
        """Parse a single ``<JOB_NAME>`` element into an :class:`SftpJob`.

        Args:
            element: The XML element representing the job.
            name: The tag name (used as the job name).
        """
        sid_text = self._text(element, "ServicerID")
        da_text = self._text(element, "DayAdjust")
        sid_int = self._parse_int(sid_text) if sid_text else 0

        return SftpJob(
            name=name,
            path=self._text(element, "Path") or "",
            servicer_id=sid_int if sid_int is not None else 0,
            dsn=self._text(element, "DSN") or "",
            sme=self._text(element, "SME") or "",
            save_location=self._text(element, "SaveLocation") or "",
            skip_list=self._text(element, "SkipList") or "",
            ignore_list=self._text(element, "IgnoreList") or "",
            parsers=self._child_dict(element, "Parsers"),
            zip_content_filter=self._text(element, "ZipContentFilter") or "",
            templates=self._child_dict(element, "Templates"),
            day_adjust=self._parse_int(da_text) if da_text else None,
        )

    # ------------------------------------------------------------------ #
    #  Infrastructure
    # ------------------------------------------------------------------ #

    def get_infrastructure(self) -> dict:
        """Extract top-level infrastructure settings from the XML.

        Returns a dict with keys such as ``DisableJob``, ``Server``,
        ``Db``, ``StagingServer``, ``StagingDb``, ``HashiAPI``, ``Email``,
        ``MapDrives``, and Outlook-level settings (``Enabled``,
        ``CredFileLocation``).
        """
        infra: Dict[str, object] = {}

        # Simple top-level scalars – may be at root level (repo sample)
        # or inside a second <MapDrives> element (production layout).
        _INFRA_TAGS = ("Server", "Db", "StagingServer", "StagingDb", "HashiAPI")

        # DisableJob is always at root
        dj = self.root.find("DisableJob")
        infra["DisableJob"] = dj.text if dj is not None and dj.text else None

        # Try root first
        for tag in _INFRA_TAGS:
            el = self.root.find(tag)
            infra[tag] = el.text if el is not None and el.text else None

        # MapDrives – production may have TWO <MapDrives> blocks:
        #   1st = drive letters, 2nd = Server/Db/StagingServer/etc.
        drive_map: Dict[str, str] = {}
        for md_el in self.root.findall("MapDrives"):
            for child in md_el:
                if child.tag in _INFRA_TAGS:
                    # Found infra tags inside MapDrives – override if
                    # not already found at root level
                    if infra.get(child.tag) is None and child.text:
                        infra[child.tag] = child.text.strip()
                else:
                    drive_map[child.tag] = (child.text or "").strip()
        infra["MapDrives"] = drive_map

        # Email block
        email_el = self.root.find("Email")
        if email_el is not None:
            infra["Email"] = {
                child.tag: (child.text or "") for child in email_el
            }
        else:
            infra["Email"] = {}

        # Outlook-level settings (not the job collections)
        outlook = self.root.find("Outlook")
        if outlook is not None:
            infra["Outlook_Enabled"] = self._text(outlook, "Enabled")
            infra["Outlook_CredFileLocation"] = self._text(
                outlook, "CredFileLocation"
            )
        else:
            infra["Outlook_Enabled"] = None
            infra["Outlook_CredFileLocation"] = None

        return infra

    def get_element_tree(self) -> ET.ElementTree:
        """Return the parsed :class:`~xml.etree.ElementTree.ElementTree`.

        Useful when callers need to modify and write the tree back to disk.
        """
        return self.tree

    # ------------------------------------------------------------------ #
    #  Internal utilities
    # ------------------------------------------------------------------ #

    @staticmethod
    def _text(parent: ET.Element, tag: str) -> Optional[str]:
        """Return stripped text of *tag* under *parent*, or ``None``."""
        el = parent.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        return None

    @staticmethod
    def _child_dict(parent: ET.Element, tag: str) -> Dict[str, str]:
        """Return ``{child.tag: child.text}`` for every child of *tag*."""
        el = parent.find(tag)
        if el is None:
            return {}
        return {child.tag: (child.text or "") for child in el}

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        """Parse *value* as ``int``, returning ``None`` on failure."""
        if value is None:
            return None
        try:
            return int(value.strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_bool(value: Optional[str]) -> Optional[bool]:
        """Parse ``"True"``/``"False"`` strings to ``bool``."""
        if value is None:
            return None
        return value.strip().lower() == "true"

    @staticmethod
    def _looks_like_timestamp(value: str) -> bool:
        """Heuristic check – does *value* look like a date/time string?"""
        # Accept common patterns: ISO-8601-ish, US-date, or slash-date
        # with at least a date portion (e.g. "2024-01-15 09:30:00").
        return bool(
            re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value)
            or re.search(r"\d{1,2}/\d{1,2}/\d{4}", value)
        )
