"""Deterministic job cloning helpers for Settings.xml."""

from __future__ import annotations

import copy
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .parser import SettingsXmlParser
from .writer import XmlWriter

logger = logging.getLogger("frp.xml.clone")

JOB_NAME_FIELD = "@job_name"
_XML_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_PATH_SEGMENT_RE = re.compile(r"^(?P<tag>[^\[]+?)(?:\[(?P<index>\d+)\])?$")


@dataclass
class ResolvedCloneSource:
    """Source job resolution across email and SFTP settings."""

    xml_type: str
    settings_path: str
    parser: SettingsXmlParser
    tree: ET.ElementTree
    collection: ET.Element
    source_element: ET.Element


class JobCloneEngine:
    """Prepare, preview, and apply deterministic job clones."""

    def __init__(self, settings_path: str, sftp_settings_path: Optional[str] = None) -> None:
        self.settings_path = settings_path
        self.sftp_settings_path = sftp_settings_path

    def prepare_clone(self, source_servicer_id: int) -> Dict[str, object]:
        resolved = self._resolve_source(source_servicer_id)
        assigned_servicer_id = self._next_available_servicer_id(source_servicer_id)
        proposed_job_name = self._build_proposed_job_name(
            resolved.source_element.tag,
            assigned_servicer_id,
            resolved.collection,
        )

        editable_fields = [
            {
                "path": JOB_NAME_FIELD,
                "label": "JobName",
                "current_value": resolved.source_element.tag,
                "suggested_value": proposed_job_name,
            }
        ]
        editable_fields.extend(self._collect_leaf_fields(resolved.source_element))

        return {
            "source_servicer_id": source_servicer_id,
            "source_job_name": resolved.source_element.tag,
            "source_xml_type": resolved.xml_type,
            "source_settings_path": resolved.settings_path,
            "assigned_servicer_id": assigned_servicer_id,
            "proposed_job_name": proposed_job_name,
            "editable_fields": editable_fields,
            "total_editable_fields": len(editable_fields),
        }

    def preview_clone(
        self,
        source_servicer_id: int,
        clone_job_name: str,
        assigned_servicer_id: int,
        overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        resolved = self._resolve_source(source_servicer_id)
        overrides = overrides or {}
        clone_el, changes = self._build_clone_element(
            resolved,
            clone_job_name,
            assigned_servicer_id,
            overrides,
        )
        preview_xml = self._serialize_element(clone_el)

        return {
            "source_servicer_id": source_servicer_id,
            "source_job_name": resolved.source_element.tag,
            "job_name": clone_job_name,
            "xml_type": resolved.xml_type,
            "assigned_servicer_id": assigned_servicer_id,
            "changes": changes,
            "preview_xml": preview_xml,
        }

    def apply_clone(
        self,
        source_servicer_id: int,
        clone_job_name: str,
        assigned_servicer_id: int,
        overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        resolved = self._resolve_source(source_servicer_id)
        overrides = overrides or {}
        clone_el, changes = self._build_clone_element(
            resolved,
            clone_job_name,
            assigned_servicer_id,
            overrides,
        )

        resolved.collection.append(clone_el)

        writer = XmlWriter(resolved.settings_path)
        save_result = writer.save(resolved.tree)
        if not save_result.get("success"):
            raise RuntimeError(save_result.get("message", "Clone save failed"))

        validation = SettingsXmlParser(resolved.settings_path).validate().to_dict()
        return {
            "operation": "clone",
            "source_servicer_id": source_servicer_id,
            "source_job_name": resolved.source_element.tag,
            "job_name": clone_job_name,
            "xml_type": resolved.xml_type,
            "assigned_servicer_id": assigned_servicer_id,
            "changes": changes,
            "backup_file": save_result.get("backup_path", ""),
            "validation": validation,
        }

    def _resolve_source(self, source_servicer_id: int) -> ResolvedCloneSource:
        matches: List[ResolvedCloneSource] = []
        for xml_type, settings_path in self._iter_candidate_settings():
            parser = SettingsXmlParser(settings_path)
            tree = parser.get_element_tree()
            collection = self._get_collection(parser, xml_type)
            if collection is None:
                continue
            for child in collection:
                sid = self._safe_int(self._find_text(child, "ServicerID"))
                if sid == source_servicer_id:
                    matches.append(
                        ResolvedCloneSource(
                            xml_type=xml_type,
                            settings_path=settings_path,
                            parser=parser,
                            tree=tree,
                            collection=collection,
                            source_element=child,
                        )
                    )

        if not matches:
            raise ValueError(f"No job found with ServicerID {source_servicer_id}.")
        if len(matches) > 1:
            labels = ", ".join(f"{m.xml_type}:{m.source_element.tag}" for m in matches)
            raise ValueError(
                f"ServicerID {source_servicer_id} is not unique across configured XML files: {labels}"
            )
        return matches[0]

    def _build_clone_element(
        self,
        resolved: ResolvedCloneSource,
        clone_job_name: str,
        assigned_servicer_id: int,
        overrides: Dict[str, str],
    ) -> Tuple[ET.Element, List[Dict[str, str]]]:
        self._validate_job_name(clone_job_name)
        self._ensure_job_name_available(resolved.collection, clone_job_name)
        self._ensure_servicer_id_available(assigned_servicer_id, resolved.source_element)

        clone_el = copy.deepcopy(resolved.source_element)
        source_job_name = resolved.source_element.tag
        changes: List[Dict[str, str]] = []

        if clone_job_name != source_job_name:
            changes.append({
                "field": "JobName",
                "old_value": source_job_name,
                "new_value": clone_job_name,
            })
        clone_el.tag = clone_job_name

        name_el = clone_el.find("Name")
        if name_el is not None:
            old_name = name_el.text or ""
            name_el.text = clone_job_name
            if old_name != clone_job_name and old_name != source_job_name:
                changes.append({
                    "field": "Name",
                    "old_value": old_name,
                    "new_value": clone_job_name,
                })

        servicer_el = clone_el.find("ServicerID")
        if servicer_el is None:
            servicer_el = ET.SubElement(clone_el, "ServicerID")
            old_servicer_id = ""
        else:
            old_servicer_id = servicer_el.text or ""
        servicer_el.text = str(assigned_servicer_id)
        changes.append({
            "field": "ServicerID",
            "old_value": old_servicer_id,
            "new_value": str(assigned_servicer_id),
        })

        for path, new_value in overrides.items():
            if path == JOB_NAME_FIELD:
                continue
            current_el = self._find_by_path(clone_el, path)
            if current_el is None:
                raise ValueError(
                    f"Clone source changed and no longer contains field '{path}'. Restart /clone."
                )
            old_value = current_el.text or ""
            if old_value == str(new_value):
                continue
            current_el.text = str(new_value)
            changes.append({
                "field": path,
                "old_value": old_value,
                "new_value": str(new_value),
            })

        return clone_el, changes

    def _iter_candidate_settings(self) -> Iterable[Tuple[str, str]]:
        if self.settings_path:
            yield "email", self.settings_path
        if self.sftp_settings_path:
            yield "sftp", self.sftp_settings_path

    def _next_available_servicer_id(self, source_servicer_id: int) -> int:
        used_ids = set()
        for _xml_type, settings_path in self._iter_candidate_settings():
            parser = SettingsXmlParser(settings_path)
            for job in parser.get_all_jobs():
                servicer_id = getattr(job, "servicer_id", None)
                if servicer_id is None:
                    continue
                try:
                    used_ids.add(int(servicer_id))
                except (TypeError, ValueError):
                    continue

        candidate = source_servicer_id + 1
        while candidate in used_ids:
            candidate += 1
        return candidate

    def _build_proposed_job_name(
        self,
        source_job_name: str,
        assigned_servicer_id: int,
        collection: ET.Element,
    ) -> str:
        existing = {child.tag for child in collection}
        base_name = f"{source_job_name}_{assigned_servicer_id}"
        if base_name not in existing:
            return base_name

        suffix = 2
        while True:
            candidate = f"{base_name}_{suffix}"
            if candidate not in existing:
                return candidate
            suffix += 1

    def _ensure_job_name_available(self, collection: ET.Element, clone_job_name: str) -> None:
        for child in collection:
            if child.tag == clone_job_name:
                raise ValueError(f"Job '{clone_job_name}' already exists in XML.")

    def _ensure_servicer_id_available(self, assigned_servicer_id: int, source_element: ET.Element) -> None:
        for _xml_type, settings_path in self._iter_candidate_settings():
            parser = SettingsXmlParser(settings_path)
            collection = self._get_collection(parser, parser.detect_xml_type())
            if collection is None:
                continue
            for child in collection:
                if child is source_element:
                    continue
                existing = self._safe_int(self._find_text(child, "ServicerID"))
                if existing == assigned_servicer_id:
                    raise ValueError(
                        f"Assigned ServicerID {assigned_servicer_id} is already in use. Restart /clone to recalculate."
                    )

    def _collect_leaf_fields(self, source_element: ET.Element) -> List[Dict[str, str]]:
        fields: List[Dict[str, str]] = []

        def visit(node: ET.Element, parent_path: str = "") -> None:
            sibling_counts: Dict[str, int] = {}
            sibling_seen: Dict[str, int] = {}
            for child in node:
                sibling_counts[child.tag] = sibling_counts.get(child.tag, 0) + 1
            for child in node:
                sibling_seen[child.tag] = sibling_seen.get(child.tag, 0) + 1
                suffix = f"[{sibling_seen[child.tag]}]" if sibling_counts[child.tag] > 1 else ""
                segment = f"{child.tag}{suffix}"
                path = segment if not parent_path else f"{parent_path}/{segment}"
                if len(child):
                    visit(child, path)
                    continue

                if child.tag in {"ServicerID", "Name"}:
                    continue
                fields.append(
                    {
                        "path": path,
                        "label": child.tag,
                        "current_value": child.text or "",
                    }
                )

        visit(source_element)
        return fields

    @staticmethod
    def _serialize_element(element: ET.Element) -> str:
        preview = copy.deepcopy(element)
        ET.indent(preview, space="  ")
        return ET.tostring(preview, encoding="unicode")

    @staticmethod
    def _get_collection(parser: SettingsXmlParser, xml_type: str) -> Optional[ET.Element]:
        if xml_type == "email":
            return parser._find_collection("MailboxCollection")
        if xml_type == "sftp":
            return parser._find_collection("FolderCollection")
        return None

    @staticmethod
    def _find_text(element: ET.Element, tag: str) -> Optional[str]:
        child = element.find(tag)
        if child is None:
            return None
        return child.text or ""

    @staticmethod
    def _safe_int(value: Optional[str]) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_job_name(job_name: str) -> None:
        if not job_name:
            raise ValueError("Clone job name cannot be empty.")
        if not _XML_NAME_RE.match(job_name):
            raise ValueError(
                "Clone job name must be a valid XML tag: letters/numbers/underscore/dot/hyphen only, and it must not start with a number."
            )

    @staticmethod
    def _find_by_path(root: ET.Element, path: str) -> Optional[ET.Element]:
        current = root
        for raw_segment in path.split("/"):
            match = _PATH_SEGMENT_RE.match(raw_segment)
            if not match:
                return None
            tag = match.group("tag")
            index = int(match.group("index") or "1")
            matches = [child for child in current if child.tag == tag]
            if len(matches) < index:
                return None
            current = matches[index - 1]
        return current