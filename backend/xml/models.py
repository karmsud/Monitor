"""Data-class models for email and SFTP job definitions parsed from Settings.xml."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Stop-words stripped when tokenising a natural-language search query so that
# passing e.g. "list all jobs that have save location tpmt" still matches.
_STOP_WORDS = frozenset(
    # common English stop words
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might must can could all any both each "
    "every few more most other some such that these those this what which "
    "who whom whose how where when why with without for from of on in to "
    "and or not no by at it its i me my give tell about them their "
    # verbs users naturally say when querying
    "list show find get search display look check "
    # field-descriptor words (describe columns, not data values)
    "job jobs name named save location path folder file email sender "
    "filter template servicer mailbox subject sme queue deal type sftp".split()
)


def _match_mode(parsers: Dict[str, Any]) -> str:
    """Derive MatchMode from parser configuration.

    - 'Subject' → DetachFileSubject parser (keyword matches email subject line)
    - 'Filename' → DetachFile / MoveFile / MoveFile2 parser (keyword matches attachment filename)
    - 'Both' → has both DetachFileSubject and DetachFile
    - '(none)' → no recognised parser
    """
    names = {k.lower() for k in parsers}
    has_subject = "detachfilesubject" in names
    has_file = "detachfile" in names or "movefile" in names or "movefile2" in names
    if has_subject and has_file:
        return "Both"
    if has_subject:
        return "Subject"
    if has_file:
        return "Filename"
    return "(none)"


def _match_mode_description(mode: str) -> str:
    """Return a human-friendly explanation of the match mode."""
    _DESCRIPTIONS = {
        "Subject": "Detects files by matching a keyword in the email subject line",
        "Filename": "Detects files by matching the attachment filename",
        "Both": "Matches on both email subject line and attachment filename",
    }
    return _DESCRIPTIONS.get(mode, "No recognised parser configured")


def _tokenized_match(query: str, searchable: List[str]) -> bool:
    """Return True if *query* matches the searchable fields.

    Strategy:
    1. If the raw query is a substring of any field → match (backward compat).
    2. Tokenise the query, drop stop-words, and require ALL remaining tokens
       to appear as substrings somewhere across the fields.
    3. Fallback: if step 2 yields no matches because too many tokens were
       kept, try matching any token of 3+ characters.
    """
    q = query.strip().lower()
    haystack = "\n".join(s.lower() for s in searchable)

    # Fast path: exact substring
    if q in haystack:
        return True

    # Tokenised path — ALL meaningful tokens must appear
    tokens = [t for t in q.split() if t not in _STOP_WORDS and len(t) >= 2]
    if not tokens:
        # Every word was a stop-word — the caller's intent was generic
        # (e.g. "list all jobs").  Return True so the job is included.
        return True
    if all(t in haystack for t in tokens):
        return True

    # Fallback: ANY token of 3+ chars matches (catches cases where some
    # tokens are field descriptors we didn't anticipate as stop-words)
    long_tokens = [t for t in tokens if len(t) >= 3]
    return any(t in haystack for t in long_tokens) if long_tokens else False


# --------------------------------------------------------------------------- #
#  EmailJob
# --------------------------------------------------------------------------- #

@dataclass
class EmailJob:
    """Represents a single email-based job entry in Settings.xml."""

    name: str
    mailbox: str
    folder: str
    sme: str
    last_email: Optional[str] = None
    save_location: str = ""
    filters: Dict[str, Any] = field(default_factory=dict)
    parsers: Dict[str, Any] = field(default_factory=dict)
    servicer_id: Optional[int] = None
    queue_one_file: Optional[bool] = None
    templates: Dict[str, Any] = field(default_factory=dict)
    day_adjust: Optional[int] = None
    xml_type: str = "email"

    # -- helpers ---------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for JSON serialisation."""
        return asdict(self)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a curated summary suitable for LLM presentation.

        Includes only the operationally relevant fields:
        JobName, Mailbox, Sender, ServicerID, SavePath,
        Template, MatchMode, QueueOneFile.
        """
        sender = self.filters.get("From", "").strip()
        template = ""
        if self.templates:
            template = self.templates.get("Main", "") or next(
                (v for v in self.templates.values() if v), ""
            )
        return {
            "job_name": self.name,
            "mailbox": self.mailbox,
            "sender": sender or "(not specified)",
            "servicer_id": self.servicer_id,
            "save_path": self.save_location,
            "scrubber": template or "(none)",
            "match_mode": _match_mode(self.parsers),
            "match_mode_description": _match_mode_description(_match_mode(self.parsers)),
            "queue_one_file": self.queue_one_file,
            "xml_type": self.xml_type,
        }

    def matches_query(self, query: str) -> bool:
        """Return *True* if *query* matches any searchable field.

        Supports both exact-substring and tokenised natural-language queries.
        """
        searchable = [
            self.name,
            self.mailbox,
            self.folder,
            self.sme,
            self.last_email or "",
            self.save_location,
            str(self.servicer_id) if self.servicer_id is not None else "",
            str(self.filters),
            str(self.parsers),
            str(self.templates),
            self.xml_type,
        ]
        return _tokenized_match(query, searchable)


# --------------------------------------------------------------------------- #
#  SftpJob
# --------------------------------------------------------------------------- #

@dataclass
class SftpJob:
    """Represents a single SFTP-based job entry in Settings.xml."""

    name: str
    path: str
    servicer_id: int
    dsn: str
    sme: str
    save_location: str = ""
    skip_list: str = ""
    ignore_list: str = ""
    parsers: Dict[str, Any] = field(default_factory=dict)
    zip_content_filter: str = ""
    templates: Dict[str, Any] = field(default_factory=dict)
    day_adjust: Optional[int] = None
    xml_type: str = "sftp"

    # -- helpers ---------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for JSON serialisation."""
        return asdict(self)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a curated summary suitable for LLM presentation."""
        template = ""
        if self.templates:
            template = self.templates.get("Main", "") or next(
                (v for v in self.templates.values() if v), ""
            )
        return {
            "job_name": self.name,
            "sftp_path": self.path,
            "dsn": self.dsn,
            "servicer_id": self.servicer_id,
            "save_path": self.save_location,
            "scrubber": template or "(none)",
            "match_mode": _match_mode(self.parsers),
            "match_mode_description": _match_mode_description(_match_mode(self.parsers)),
            "zip_filter": self.zip_content_filter or "(none)",
            "xml_type": self.xml_type,
        }

    def matches_query(self, query: str) -> bool:
        """Return *True* if *query* matches any searchable field.

        Supports both exact-substring and tokenised natural-language queries.
        """
        searchable = [
            self.name,
            self.path,
            str(self.servicer_id),
            self.dsn,
            self.sme,
            self.save_location,
            self.skip_list,
            self.ignore_list,
            str(self.parsers),
            self.zip_content_filter,
            str(self.templates),
            self.xml_type,
        ]
        return _tokenized_match(query, searchable)


# --------------------------------------------------------------------------- #
#  ValidationResult
# --------------------------------------------------------------------------- #

@dataclass
class ValidationResult:
    """Aggregated validation outcome for a Settings.xml file."""

    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    xml_type: str = "email"
    job_count: int = 0

    # -- helpers ---------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for JSON serialisation."""
        return asdict(self)

    def add_error(self, message: str) -> None:
        """Record an error and mark the result as invalid."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Record a non-fatal warning."""
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        """Record an informational note."""
        self.info.append(message)


# --------------------------------------------------------------------------- #
#  JobTemplate
# --------------------------------------------------------------------------- #

@dataclass
class JobTemplate:
    """Describes a reusable job configuration pattern."""

    pattern_name: str
    parser_names: List[str]
    template_names: List[str]
    mailbox_pattern: str
    example_job_name: str
    job_count: int
    has_servicer_id: bool
    sample_fields: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
#  FieldChange
# --------------------------------------------------------------------------- #

@dataclass
class FieldChange:
    """A single field-level change within a job."""

    field: str
    old_value: str
    new_value: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
#  JobDiff
# --------------------------------------------------------------------------- #

@dataclass
class JobDiff:
    """Describes one job's change status in a diff."""

    job_name: str
    change_type: str  # "added" | "removed" | "modified"
    field_changes: List['FieldChange'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_name": self.job_name,
            "change_type": self.change_type,
            "field_changes": [fc.to_dict() for fc in self.field_changes],
        }


# --------------------------------------------------------------------------- #
#  DiffResult
# --------------------------------------------------------------------------- #

@dataclass
class DiffResult:
    """Complete diff between two Settings.xml files."""

    current_file: str
    backup_file: str
    added_jobs: List[JobDiff] = field(default_factory=list)
    removed_jobs: List[JobDiff] = field(default_factory=list)
    modified_jobs: List[JobDiff] = field(default_factory=list)
    unchanged_count: int = 0
    timestamp: str = ""

    @property
    def total_changes(self) -> int:
        return len(self.added_jobs) + len(self.removed_jobs) + len(self.modified_jobs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_file": self.current_file,
            "backup_file": self.backup_file,
            "added": [j.to_dict() for j in self.added_jobs],
            "removed": [j.to_dict() for j in self.removed_jobs],
            "modified": [j.to_dict() for j in self.modified_jobs],
            "unchanged_count": self.unchanged_count,
            "total_changes": self.total_changes,
            "timestamp": self.timestamp,
        }


# --------------------------------------------------------------------------- #
#  CrudResult
# --------------------------------------------------------------------------- #

@dataclass
class CrudResult:
    """Result of a create or edit operation."""

    operation: str  # "create" | "edit"
    job_name: str
    changes: List[FieldChange] = field(default_factory=list)
    backup_file: str = ""
    validation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "job_name": self.job_name,
            "changes": [c.to_dict() for c in self.changes],
            "backup_file": self.backup_file,
            "validation": self.validation,
        }
