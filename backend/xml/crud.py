"""CRUD engine for creating and editing jobs in Settings.xml."""

from __future__ import annotations

import copy
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .models import CrudResult, FieldChange
from .parser import SettingsXmlParser
from .writer import XmlWriter

logger = logging.getLogger("frp.xml.crud")

# --------------------------------------------------------------------------- #
#  Field-name → XML element-name mappings
# --------------------------------------------------------------------------- #

EMAIL_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "mailbox": "Mailbox",
    "mailbox_address": "Mailbox",
    "folder": "Folder",
    "sme": "SME",
    "save_location": "SaveLocation",
    "last_email": "LastEmail",
    "queue_one_file": "QueueOneFile",
    "day_adjust": "DayAdjust",
    "import_did": "ImportDID",
    "subject_filter": "SubjectFilter",
    "sender_filter": "Filters/From",
    # Scrubber / template — stored as <Templates><Main>VALUE</Main></Templates>
    "scrubber": "Templates/Main",
    "template": "Templates/Main",
    "templates_main": "Templates/Main",
}

SFTP_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "path": "Path",
    "dsn": "DSN",
    "sme": "SME",
    "save_location": "SaveLocation",
    "skip_list": "SkipList",
    "ignore_list": "IgnoreList",
    "zip_content_filter": "ZipContentFilter",
    "day_adjust": "DayAdjust",
}


class JobCrudEngine:
    """Create and edit jobs within a Settings.xml file.

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
        self._field_map = EMAIL_FIELD_MAP if xml_type == "email" else SFTP_FIELD_MAP

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def create_job(
        self,
        template_job_name: str,
        new_job_name: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> CrudResult:
        """Clone *template_job_name* as *new_job_name* with optional overrides.

        Returns a :class:`CrudResult` describing the operation.
        """
        parser = SettingsXmlParser(self.settings_path)
        tree = parser.get_element_tree()
        root = tree.getroot()

        # Find template element
        template_el = self._find_job_element(root, template_job_name)
        if template_el is None:
            raise ValueError(
                f"Template job '{template_job_name}' not found in XML"
            )

        # Ensure new name doesn't already exist
        if self._find_job_element(root, new_job_name) is not None:
            raise ValueError(f"Job '{new_job_name}' already exists in XML")

        # Deep copy and rename the element
        new_el = copy.deepcopy(template_el)
        new_el.tag = new_job_name

        # Update Name child element
        name_el = new_el.find("Name")
        if name_el is not None:
            name_el.text = new_job_name

        # Track changes
        changes: List[FieldChange] = []

        # Apply overrides
        if overrides:
            for field_name, new_value in overrides.items():
                xml_tag = self._field_map.get(field_name, field_name)
                child = new_el.find(xml_tag)
                old_value = ""
                if child is not None:
                    old_value = child.text or ""
                    child.text = str(new_value)
                else:
                    # Create new sub-element
                    child = ET.SubElement(new_el, xml_tag)
                    child.text = str(new_value)
                changes.append(FieldChange(
                    field=field_name,
                    old_value=old_value,
                    new_value=str(new_value),
                ))

        # Add to collection
        collection = self._get_collection_element(root)
        if collection is None:
            raise ValueError(
                f"Collection element not found in XML for type '{self.xml_type}'"
            )
        collection.append(new_el)

        # Save
        writer = XmlWriter(self.settings_path)
        save_result = writer.save(tree)

        if not save_result.get("success"):
            raise RuntimeError(
                f"Failed to save XML: {save_result.get('message', 'unknown error')}"
            )

        # Validate after save
        new_parser = SettingsXmlParser(self.settings_path)
        validation = new_parser.validate()

        return CrudResult(
            operation="create",
            job_name=new_job_name,
            changes=changes,
            backup_file=save_result.get("backup_path", ""),
            validation=validation.to_dict(),
        )

    def edit_job(
        self,
        job_name: str,
        field_name: str,
        new_value: str,
    ) -> CrudResult:
        """Edit a single field on an existing job.

        Returns a :class:`CrudResult` describing the operation.
        """
        parser = SettingsXmlParser(self.settings_path)
        tree = parser.get_element_tree()
        root = tree.getroot()

        job_el = self._find_job_element(root, job_name)
        if job_el is None:
            # Try fuzzy match
            suggestions = self._fuzzy_find_jobs(root, job_name)
            hint = ""
            if suggestions:
                hint = f" Did you mean: {', '.join(suggestions[:5])}?"
            raise ValueError(f"Job '{job_name}' not found in XML.{hint}")

        xml_tag = self._field_map.get(field_name, field_name)
        child = job_el.find(xml_tag)
        old_value = ""

        if child is not None:
            old_value = child.text or ""
            child.text = str(new_value)
        elif "/" in xml_tag:
            # Nested path e.g. "Templates/Main" — find-or-create each level
            parts = xml_tag.split("/")
            parent = job_el
            for part in parts[:-1]:
                existing = parent.find(part)
                if existing is None:
                    existing = ET.SubElement(parent, part)
                parent = existing
            child = ET.SubElement(parent, parts[-1])
            child.text = str(new_value)
        else:
            child = ET.SubElement(job_el, xml_tag)
            child.text = str(new_value)

        change = FieldChange(
            field=field_name,
            old_value=old_value,
            new_value=str(new_value),
        )

        # Save
        writer = XmlWriter(self.settings_path)
        save_result = writer.save(tree)

        if not save_result.get("success"):
            raise RuntimeError(
                f"Failed to save XML: {save_result.get('message', 'unknown error')}"
            )

        # Validate after save
        new_parser = SettingsXmlParser(self.settings_path)
        validation = new_parser.validate()

        return CrudResult(
            operation="edit",
            job_name=job_name,
            changes=[change],
            backup_file=save_result.get("backup_path", ""),
            validation=validation.to_dict(),
        )

    def get_job_preview(self, job_name: str) -> dict:
        """Return a dict preview of a job's current XML fields.

        Raises :class:`ValueError` if the job is not found.
        """
        parser = SettingsXmlParser(self.settings_path)
        tree = parser.get_element_tree()
        root = tree.getroot()

        job_el = self._find_job_element(root, job_name)
        if job_el is None:
            raise ValueError(f"Job '{job_name}' not found in XML")

        preview: Dict[str, Any] = {"_tag": job_el.tag}
        for child in job_el:
            if len(child) == 0:
                preview[child.tag] = child.text or ""
            else:
                # Sub-elements (e.g. Parsers, Templates)
                preview[child.tag] = {
                    sub.tag: sub.text or "" for sub in child
                }
        return preview

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _find_job_element(
        self, root: ET.Element, name: str
    ) -> Optional[ET.Element]:
        """Locate a job element by its XML tag name (case-sensitive)."""
        collection = self._get_collection_element(root)
        if collection is None:
            return None
        for child in collection:
            if child.tag == name:
                return child
            # Also check <Name> sub-element
            name_el = child.find("Name")
            if name_el is not None and name_el.text == name:
                return child
        return None

    def _fuzzy_find_jobs(self, root: ET.Element, query: str) -> list:
        """Return job tag names that partially match *query* (case-insensitive)."""
        collection = self._get_collection_element(root)
        if collection is None:
            return []
        q = query.lower()
        matches = []
        for child in collection:
            if q in child.tag.lower():
                matches.append(child.tag)
            else:
                name_el = child.find("Name")
                if name_el is not None and name_el.text and q in name_el.text.lower():
                    matches.append(child.tag)
        return matches

    def _get_collection_element(
        self, root: ET.Element
    ) -> Optional[ET.Element]:
        """Return the appropriate collection element based on xml_type."""
        if self.xml_type == "email":
            return root.find(".//MailboxCollection")
        else:
            return root.find(".//FolderCollection")
