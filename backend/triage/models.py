"""Data-class models for the email triage pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EmailInfo:
    """Metadata extracted from a .msg file."""

    sender: str
    sender_name: str
    subject: str
    date: str
    to: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    body_preview: str = ""
    attachment_names: List[str] = field(default_factory=list)
    file_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_safe_dict(self) -> Dict[str, Any]:
        """Return a dict that omits the full sender address."""
        return {
            "sender_domain": self.sender.split("@")[-1] if "@" in self.sender else "",
            "sender_name": self.sender_name,
            "subject": self.subject,
            "date": self.date,
            "attachment_count": len(self.attachment_names),
            "attachment_names": self.attachment_names,
        }


@dataclass
class MatchResult:
    """A single job match against an email."""

    job_name: str
    xml_type: str
    match_type: str         # "mailbox"|"sender"|"subject"|"both"
    match_confidence: str   # "exact"|"partial"
    servicer_id: Optional[str]
    matched_filter: str
    email_field_matched: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def sort_score(self) -> int:
        """Higher is better: both > mailbox > sender > subject, exact > partial."""
        type_score = {"both": 4, "mailbox": 3, "sender": 2, "subject": 1}.get(self.match_type, 0)
        conf_score = {"exact": 2, "partial": 1}.get(self.match_confidence, 0)
        return type_score * 10 + conf_score


@dataclass
class DIDMatch:
    """A single ImportDID keyword matched against email content."""

    did: str
    import_did: str
    matched_in: str  # "filename" | "subject"
    matched_value: str  # the actual filename or subject text that matched

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TriageResult:
    """Complete result of an email triage operation."""

    email_info: EmailInfo
    matches: List[MatchResult] = field(default_factory=list)
    has_match: bool = False
    coverage_status: Optional[str] = None
    did_count: Optional[int] = None
    deals: Optional[List[Dict[str, Any]]] = None
    did_matches: List[DIDMatch] = field(default_factory=list)
    log_summary: Optional[Dict[str, Any]] = None
    template_status: Optional[Dict[str, Any]] = None
    suggested_template: Optional[str] = None
    suggested_config: Optional[Dict[str, Any]] = None
    recommendation: str = ""
    confidence: str = ""  # monitored | should_process | processed | completed | failed

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["email_info"] = self.email_info.to_dict()
        d["matches"] = [m.to_dict() for m in self.matches]
        d["did_matches"] = [dm.to_dict() for dm in self.did_matches]
        return d
