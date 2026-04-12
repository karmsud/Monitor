# Phase 1: Technical Design
## Implementation-Ready Specifications

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Complete implementation specifications with code contracts

---

## Table of Contents
1. [Overview](#overview)
2. [Python Data Models](#python-data-models)
3. [XML Parser Engine](#xml-parser-engine)
4. [XML Writer & Backup Engine](#xml-writer--backup-engine)
5. [Dual Mode Database Connector](#dual-mode-database-connector)
6. [Deal Repository](#deal-repository)
7. [Log File Parser](#log-file-parser)
8. [SQLite Log Indexer](#sqlite-log-indexer)
9. [CLI Entry Point](#cli-entry-point)
10. [Extension JavaScript Contracts](#extension-javascript-contracts)
11. [Chat Participant Handler](#chat-participant-handler)
12. [Configuration](#configuration)
13. [Error Handling Strategy](#error-handling-strategy)

---

## Overview

This document provides complete, implementation-ready specifications for every Phase 1 component. All code includes:
- Type hints
- Docstrings with Args/Returns/Raises
- Error handling and logging
- JSON-serializable output for CLI bridge

### File Manifest

```
backend/
├── __init__.py
├── xml/
│   ├── __init__.py
│   ├── parser.py                  # ~400 lines — XML read, search, validate
│   ├── writer.py                  # ~150 lines — XML write, backup management
│   └── models.py                  # ~200 lines — EmailJob, SftpJob, ValidationResult
├── db/
│   ├── __init__.py
│   ├── connection.py              # ~80 lines  — Factory pattern (prod/dev)
│   ├── connection_mysql.py        # ~60 lines  — MySQL pyodbc connector
│   ├── connection_mssql.py        # ~60 lines  — MSSQL pyodbc connector
│   ├── queries.py                 # ~40 lines  — SQL constants
│   └── deal_repo.py              # ~120 lines — tblExternalDIDRef access layer
├── logs/
│   ├── __init__.py
│   ├── parser.py                  # ~250 lines — Log file event extraction
│   ├── indexer.py                 # ~300 lines — SQLite CRUD, sync workflow
│   └── models.py                  # ~60 lines  — LogEvent dataclass
├── backup/
│   ├── __init__.py
│   └── manager.py                 # ~120 lines — Create, list, restore backups
└── common/
    ├── __init__.py
    ├── models.py                  # ~50 lines  — Shared response models
    └── config.py                  # ~80 lines  — Backend configuration
cli/
├── __init__.py
└── main.py                        # ~250 lines — argparse, command dispatch, JSON output
config/
├── __init__.py
├── settings.py                    # ~60 lines  — Config dataclass
├── secrets_mysql.json             # ~10 lines  — Gitignored
└── secrets_mssql.json             # ~10 lines  — Gitignored
extension/
├── package.json                   # ~200 lines — Manifest
├── extension.js                   # ~120 lines — Activation
├── chat/
│   └── participant.js             # ~400 lines — @frp handler
├── copilot/
│   └── tool.js                    # ~80 lines  — runCliJson bridge
├── lib/
│   └── frp_backend.js             # ~100 lines — Runner factory
└── commands/
    ├── sync.js                    # ~40 lines  — Sync command
    └── status.js                  # ~30 lines  — Status command
```

**Total estimated lines:** ~2,700 (Python: ~1,900, JavaScript: ~800)

---

## Python Data Models

### File: `backend/xml/models.py`

```python
"""
Data models for Settings.xml job representations.

These dataclasses represent the parsed XML job elements for both
email and SFTP configurations. All models produce JSON-serializable
dictionaries via to_dict().
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict


@dataclass
class EmailJob:
    """
    Represents a single email monitoring job from Settings.xml.
    
    Serialized from <MailboxCollection> → <JOB_NAME> elements.
    
    Attributes:
        name: XML element tag name (e.g., "CMBS_GreyCo")
        mailbox: Email address for EWS connection
        folder: Mailbox folder to monitor (e.g., "Inbox")
        sme: Subject matter expert email
        last_email: Timestamp of last processed email (may be None for new jobs)
        save_location: File save path with {DealFolder}, {YYYY}, {M} tokens
        filters: Dict of filter criteria {From, Attachments, Subject}
        parsers: Dict of parser assignments {ParserType: regex_pattern}
        servicer_id: CompanyID mapping (None for shelf-level jobs)
        queue_one_file: Boolean flag (None if absent)
        templates: Dict of template assignments {TemplateName: template_value}
        day_adjust: Day offset for date calculations (None if absent)
        xml_type: Always "email" for email jobs
    """
    name: str
    mailbox: str
    folder: str
    sme: str
    last_email: Optional[str] = None
    save_location: str = ""
    filters: Dict[str, str] = field(default_factory=dict)
    parsers: Dict[str, str] = field(default_factory=dict)
    servicer_id: Optional[int] = None
    queue_one_file: Optional[bool] = None
    templates: Dict[str, str] = field(default_factory=dict)
    day_adjust: Optional[int] = None
    xml_type: str = "email"

    def to_dict(self) -> dict:
        """Return JSON-serializable dictionary."""
        return asdict(self)

    def matches_query(self, query: str) -> bool:
        """
        Check if this job matches a free-text search query.
        
        Searches across: name, mailbox, folder, sme, servicer_id,
        parser names/values, template names/values, filter values.
        
        Args:
            query: Lowercased search string
            
        Returns:
            True if any field contains the query string
        """
        searchable = [
            self.name.lower(),
            self.mailbox.lower(),
            self.folder.lower(),
            self.sme.lower(),
            self.save_location.lower(),
            str(self.servicer_id) if self.servicer_id else "",
        ]
        searchable.extend(k.lower() for k in self.parsers.keys())
        searchable.extend(v.lower() for v in self.parsers.values())
        searchable.extend(k.lower() for k in self.templates.keys())
        searchable.extend(v.lower() for v in self.templates.values())
        searchable.extend(v.lower() for v in self.filters.values())
        
        return any(query in field for field in searchable)


@dataclass
class SftpJob:
    """
    Represents a single SFTP monitoring job from Settings.xml.
    
    Serialized from <FolderCollection> → <JOB_NAME> elements.
    
    Attributes:
        name: XML element tag name (e.g., "Ocwen")
        path: SFTP source filesystem path
        servicer_id: CompanyID mapping (always present for SFTP)
        dsn: Data source name for SFTP connection
        sme: Subject matter expert email
        save_location: File save path with tokens
        skip_list: Path to skip list file
        ignore_list: Path to ignore list file
        parsers: Dict of parser assignments
        zip_content_filter: File extension filter for zip contents
        templates: Dict of template assignments (may be empty)
        day_adjust: Day adjustment value
        xml_type: Always "sftp" for SFTP jobs
    """
    name: str
    path: str
    servicer_id: int
    dsn: str
    sme: str
    save_location: str = ""
    skip_list: str = ""
    ignore_list: str = ""
    parsers: Dict[str, str] = field(default_factory=dict)
    zip_content_filter: str = ""
    templates: Dict[str, str] = field(default_factory=dict)
    day_adjust: Optional[int] = None
    xml_type: str = "sftp"

    def to_dict(self) -> dict:
        """Return JSON-serializable dictionary."""
        return asdict(self)

    def matches_query(self, query: str) -> bool:
        """
        Check if this job matches a free-text search query.
        
        Args:
            query: Lowercased search string
        Returns:
            True if any field contains the query string
        """
        searchable = [
            self.name.lower(),
            self.path.lower(),
            self.dsn.lower(),
            self.sme.lower(),
            self.save_location.lower(),
            str(self.servicer_id),
        ]
        searchable.extend(k.lower() for k in self.parsers.keys())
        searchable.extend(v.lower() for v in self.parsers.values())
        searchable.extend(k.lower() for k in self.templates.keys())
        searchable.extend(v.lower() for v in self.templates.values())
        
        return any(query in field for field in searchable)


@dataclass
class ValidationResult:
    """
    Result of Settings.xml validation.
    
    Attributes:
        valid: True if no errors found (warnings are OK)
        errors: Critical issues that must be fixed
        warnings: Non-critical issues worth reviewing
        info: Informational messages (stats, summaries)
        xml_type: "email" or "sftp"
        job_count: Total jobs found
    """
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    xml_type: str = "email"
    job_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
```

### File: `backend/logs/models.py`

```python
"""
Data models for parsed log events.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LogEvent:
    """
    A single parsed event from an email/SFTP monitor log file.
    
    Attributes:
        log_file: Source filename (e.g., "EmailMonitor_Settings.20260202102003864.log")
        log_type: "email" or "sftp"
        timestamp: ISO-8601 timestamp from log line
        job_name: Job being processed (e.g., "COOFS_LateMoney")
        mailbox: Mailbox address or SFTP path
        event_type: Event category (job_start, emails_found, email_processed, etc.)
        emails_found: Count of emails found (for emails_found event)
        subject: Email subject line (for email_processed event)
        sender: From address (for email_processed event)
        parser: Parser that matched (for parser_matched event)
        filename: File loaded/saved
        template: Template queued
        error_message: Error text (for error event)
        raw_line: Original log line text
    """
    log_file: str
    log_type: str
    timestamp: str
    job_name: Optional[str] = None
    mailbox: Optional[str] = None
    event_type: str = ""
    emails_found: Optional[int] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    parser: Optional[str] = None
    filename: Optional[str] = None
    template: Optional[str] = None
    error_message: Optional[str] = None
    raw_line: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
```

### File: `backend/common/models.py`

```python
"""
Shared response envelope for CLI output.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List
import time


@dataclass
class CliResponse:
    """
    Standard response envelope for all CLI commands.
    
    Usage:
        response = CliResponse(command="search_jobs")
        response.data = {"jobs": [...], "total_count": 5}
        print(json.dumps(response.to_dict()))
    """
    success: bool = True
    command: str = ""
    data: Optional[Any] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
```

---

## XML Parser Engine

### File: `backend/xml/parser.py`

```python
"""
Settings.xml parser for email and SFTP monitoring configurations.

Handles two XML formats:
- Email: <MailboxCollection> with email-specific job tags
- SFTP: <FolderCollection> with SFTP-specific job tags

Auto-detects format by checking for <MailboxCollection> vs <FolderCollection>.

Key Design Decisions:
- Uses xml.etree.ElementTree (Python stdlib) for zero external dependencies
- Preserves XML structure for round-trip read/write
- Returns typed dataclasses (EmailJob, SftpJob) for downstream consumers
- All search is case-insensitive
"""
import xml.etree.ElementTree as ET
import logging
import os
from typing import List, Optional, Union, Tuple
from .models import EmailJob, SftpJob, ValidationResult

logger = logging.getLogger("frp.xml.parser")


class SettingsXmlParser:
    """
    Parser for email and SFTP Settings.xml files.
    
    Usage:
        parser = SettingsXmlParser(path="/path/to/Settings.xml")
        jobs = parser.get_all_jobs()
        filtered = parser.search_jobs("rptent")
        result = parser.validate(db_servicer_ids={150, 569, 3722})
    
    Thread Safety: NOT thread-safe. Create one instance per operation.
    """

    def __init__(self, path: str):
        """
        Initialize parser by reading and parsing the XML file.
        
        Args:
            path: Absolute path to Settings.xml file
            
        Raises:
            FileNotFoundError: If path does not exist
            ET.ParseError: If XML is malformed
        """
        # ... implementation
        pass

    def detect_xml_type(self) -> str:
        """
        Auto-detect whether this is an email or SFTP Settings.xml.
        
        Returns:
            "email" if <MailboxCollection> found,
            "sftp" if <FolderCollection> found,
            "unknown" if neither found
            
        Detection Logic:
            1. Find <Outlook> element
            2. Check for <MailboxCollection> child → "email"
            3. Check for <FolderCollection> child → "sftp"
            4. Neither → "unknown"
        """
        pass

    def get_all_jobs(self) -> List[Union[EmailJob, SftpJob]]:
        """
        Parse and return ALL jobs from the Settings.xml.
        
        Returns:
            List of EmailJob or SftpJob objects (based on detected type)
            
        Implementation:
            1. detect_xml_type()
            2. If email: iterate <MailboxCollection> children → _parse_email_job()
            3. If sftp: iterate <FolderCollection> children → _parse_sftp_job()
        """
        pass

    def search_jobs(self, query: str) -> List[Union[EmailJob, SftpJob]]:
        """
        Search jobs by free-text query.
        
        Supports special keywords:
        - "shelf-level" or "no servicerid" → jobs with no ServicerID
        - "email jobs" → email-type jobs only
        - "sftp jobs" → sftp-type jobs only
        
        Args:
            query: Free-text search string
            
        Returns:
            Filtered list of matching jobs
            
        Implementation:
            1. Parse special keywords
            2. get_all_jobs()
            3. Filter via job.matches_query(query.lower())
        """
        pass

    def validate(self, db_servicer_ids: Optional[set] = None) -> ValidationResult:
        """
        Validate Settings.xml structure and content.
        
        Args:
            db_servicer_ids: Set of valid CompanyIDs from database.
                             If None, skips DB cross-reference checks.
        
        Returns:
            ValidationResult with errors, warnings, and info messages
            
        Validation Checks:
        
        ERRORS (make valid=False):
        - E001: XML parse error (malformed)
        - E002: Missing <Outlook> element
        - E003: Missing <MailboxCollection> / <FolderCollection>
        - E004: Job missing required <Mailbox> (email) or <Path> (sftp)
        - E005: Job missing required <SME>
        - E006: Job missing <Parsers> element
        - E007: Job missing <SaveLocation>
        - E008: Duplicate job names within the collection
        - E009: SFTP job missing <ServicerID>
        - E010: SFTP job missing <DSN>
        - E011: SFTP job missing <SkipList>
        - E012: SFTP job missing <IgnoreList>
        - E013: SFTP job missing <ZipContentFilter>
        
        WARNINGS:
        - W001: ServicerID in XML not found in database (if db_servicer_ids provided)
        - W002: Empty <Filters> block (email job)
        - W003: SaveLocation contains no tokens ({DealFolder}, {YYYY}, {M})
        - W004: <LastEmail> timestamp unparseable (email)
        - W005: <DayAdjust> is not a valid integer
        
        INFO:
        - I001: Total jobs found
        - I002: Jobs with ServicerID: N
        - I003: Jobs without ServicerID (shelf-level): N
        - I004: Unique ServicerIDs: N
        - I005: Unique mailboxes (email) or paths (sftp): N
        - I006: Templates in use: [list]
        """
        pass

    def _parse_email_job(self, element: ET.Element, name: str) -> EmailJob:
        """
        Parse a single email job XML element into an EmailJob.
        
        Args:
            element: The <JOB_NAME> XML element
            name: The tag name of the element (job name)
            
        Returns:
            Populated EmailJob instance
            
        Implementation Details:
        - <ServicerID>: Parse as int, None if absent or empty
        - <QueueOneFile>: Parse "True"/"False" as bool, None if absent
        - <DayAdjust>: Parse as int, None if absent or invalid
        - <Filters>: Dict from child elements {tag: text}
        - <Parsers>: Dict from child elements {tag: text}
        - <Templates>: Dict from child elements {tag: text}
        - <LastEmail>: Keep as string, None if absent
        """
        pass

    def _parse_sftp_job(self, element: ET.Element, name: str) -> SftpJob:
        """
        Parse a single SFTP job XML element into an SftpJob.
        
        Args:
            element: The <JOB_NAME> XML element
            name: The tag name of the element (job name)
            
        Returns:
            Populated SftpJob instance
            
        Implementation Details:
        - <ServicerID>: Always present for SFTP, parse as int
        - <DSN>: Always present, string
        - <SkipList>: Always present, string path
        - <IgnoreList>: Always present, string path
        - <ZipContentFilter>: Always present, string
        - <Templates>: May be absent — default to empty dict
        - <DayAdjust>: Parse as int
        """
        pass

    def get_infrastructure(self) -> dict:
        """
        Extract infrastructure settings from the XML.
        
        Returns:
            Dict with keys: disable_job, server, db, staging_server,
            staging_db, hashi_api, email_config, map_drives, cred_file
        """
        pass

    def get_element_tree(self) -> ET.ElementTree:
        """Return the parsed ElementTree for write operations."""
        pass
```

---

## XML Writer & Backup Engine

### File: `backend/xml/writer.py`

```python
"""
Settings.xml writer with automatic backup creation.

Design: Read-modify-write cycle:
1. SettingsXmlParser reads the current file
2. Caller modifies the ElementTree (add/edit/remove job)
3. XmlWriter.save() backs up current file, writes modified tree

Backup Strategy:
- Location: <Settings.xml parent>/backup/
- Pattern: Settings_{YYYYMMDD}_{HHMMSS}.xml
- Auto-creates backup/ directory if needed
"""
import xml.etree.ElementTree as ET
import os
import shutil
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("frp.xml.writer")


class XmlWriter:
    """
    Writes modified XML back to disk with automatic backup.
    
    Usage:
        parser = SettingsXmlParser(settings_path)
        tree = parser.get_element_tree()
        # ... modify tree ...
        writer = XmlWriter(settings_path)
        result = writer.save(tree)
        # result.backup_path = "C:\path\backup\Settings_20260224_143022.xml"
    """

    def __init__(self, settings_path: str):
        """
        Args:
            settings_path: Path to the Settings.xml file to overwrite
        """
        pass

    def save(self, tree: ET.ElementTree) -> dict:
        """
        Save the ElementTree to disk, creating a backup of the current file first.
        
        Args:
            tree: Modified ElementTree to write
            
        Returns:
            Dict: { 
                success: bool,
                backup_path: str (path to backup file),
                message: str (human-readable confirmation)
            }
            
        Implementation:
            1. Create backup/ directory if not exists
            2. Copy current Settings.xml → backup/Settings_{timestamp}.xml
            3. Write tree to Settings.xml with xml_declaration=True, encoding='utf-8'
            4. Verify written file is valid XML (parse it back)
            5. Return success with backup path
            
        Error Handling:
            - If backup copy fails: abort, don't write
            - If write fails: restore from backup
            - If verification fails: restore from backup, report error
        """
        pass

    def _generate_backup_filename(self) -> str:
        """
        Generate timestamped backup filename.
        
        Returns:
            Filename like "Settings_20260224_143022.xml"
        """
        now = datetime.now()
        return f"Settings_{now.strftime('%Y%m%d_%H%M%S')}.xml"
```

### File: `backend/backup/manager.py`

```python
"""
Backup file management for Settings.xml files.

Manages the backup/ subfolder alongside each Settings.xml,
providing list, count, and restore capabilities.
"""
import os
import re
import shutil
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("frp.backup")


class BackupManager:
    """
    Manages backup files for a specific Settings.xml.
    
    Usage:
        mgr = BackupManager("/path/to/Settings.xml")
        backups = mgr.list_backups()
        mgr.restore(backups[0]["filename"])
    """

    FILENAME_PATTERN = re.compile(
        r'^Settings_(\d{8})_(\d{6})\.xml$'
    )

    def __init__(self, settings_path: str):
        """
        Args:
            settings_path: Path to the active Settings.xml
        """
        self.settings_path = os.path.abspath(settings_path)
        self.backup_dir = os.path.join(os.path.dirname(self.settings_path), "backup")

    def list_backups(self) -> List[dict]:
        """
        List all backup files, sorted by timestamp (newest first).
        
        Returns:
            List of dicts: [
                {
                    "filename": "Settings_20260224_143022.xml",
                    "full_path": "C:\\path\\backup\\Settings_20260224_143022.xml",
                    "timestamp": "2026-02-24 14:30:22",
                    "size_bytes": 102400,
                    "age_days": 3
                },
                ...
            ]
        """
        pass

    def restore(self, backup_filename: str) -> dict:
        """
        Restore a backup file to become the active Settings.xml.
        
        Steps:
        1. Backup current Settings.xml (so we can undo the restore)
        2. Copy the selected backup over Settings.xml
        3. Verify the restored file is valid XML
        
        Args:
            backup_filename: Name of backup file to restore (e.g., "Settings_20260224_143022.xml")
            
        Returns:
            Dict: { success: bool, safety_backup: str, restored_from: str, message: str }
            
        Raises:
            FileNotFoundError: If backup file doesn't exist
        """
        pass

    def get_backup_count(self) -> int:
        """Return total number of backup files."""
        pass

    def get_latest_backup(self) -> Optional[dict]:
        """Return the most recent backup, or None if no backups exist."""
        pass
```

---

## Dual Mode Database Connector

### File: `backend/db/connection.py`

```python
"""
Database connection factory supporting dual-mode operation.

- prod_mode=True  → MSSQL via pyodbc (US Bank production)
- prod_mode=False → MySQL via pyodbc (local development)

Both modes use pyodbc for consistency. Connection parameters
are read from JSON secret files (gitignored).

Usage:
    conn = get_connection(prod_mode=False, secrets_path="config/secrets_mysql.json")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tblExternalDIDRef WHERE CompanyID = ?", (150,))
    rows = cursor.fetchall()
    conn.close()
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("frp.db")


def get_connection(prod_mode: bool = False, secrets_path: Optional[str] = None):
    """
    Get a database connection based on environment mode.
    
    Args:
        prod_mode: True for MSSQL production, False for MySQL local
        secrets_path: Path to secrets JSON file. If None, resolves from
                      config/ directory relative to project root.
    
    Returns:
        pyodbc.Connection object
        
    Raises:
        FileNotFoundError: If secrets file doesn't exist
        pyodbc.Error: If connection fails
        ImportError: If pyodbc not installed
        
    Connection String Construction:
    
    MySQL:
        DRIVER={driver};SERVER={server};PORT={port};DATABASE={database};UID={uid};PWD={pwd}
        
    MSSQL:
        DRIVER={driver};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};
        ENCRYPT={encrypt};TrustServerCertificate=yes
    """
    if prod_mode:
        from .connection_mssql import get_mssql_connection
        return get_mssql_connection(secrets_path)
    else:
        from .connection_mysql import get_mysql_connection
        return get_mysql_connection(secrets_path)
```

### File: `backend/db/connection_mysql.py`

```python
"""
MySQL connection via pyodbc for local development.
"""
import json
import pyodbc
import logging
import os

logger = logging.getLogger("frp.db.mysql")


def get_mysql_connection(secrets_path: str = None) -> pyodbc.Connection:
    """
    Create MySQL connection from secrets file.
    
    Args:
        secrets_path: Path to secrets_mysql.json
        
    Returns:
        pyodbc.Connection
        
    Secrets File Format:
    {
        "driver": "MySQL ODBC 8.0 Unicode Driver",
        "server": "localhost",
        "port": 3306,
        "database": "frp",
        "uid": "frp_user",
        "pwd": "local_password"
    }
    """
    if not secrets_path:
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config", "secrets_mysql.json"
        )
    
    with open(secrets_path) as f:
        secrets = json.load(f)
    
    conn_str = (
        f"DRIVER={{{secrets['driver']}}};"
        f"SERVER={secrets['server']};"
        f"PORT={secrets.get('port', 3306)};"
        f"DATABASE={secrets['database']};"
        f"UID={secrets['uid']};"
        f"PWD={secrets['pwd']}"
    )
    
    logger.info(f"Connecting to MySQL: {secrets['server']}:{secrets.get('port', 3306)}/{secrets['database']}")
    return pyodbc.connect(conn_str)
```

### File: `backend/db/connection_mssql.py`

```python
"""
MSSQL connection via pyodbc for US Bank production.
"""
import json
import pyodbc
import logging
import os

logger = logging.getLogger("frp.db.mssql")


def get_mssql_connection(secrets_path: str = None) -> pyodbc.Connection:
    """
    Create MSSQL connection from secrets file.
    
    Args:
        secrets_path: Path to secrets_mssql.json
        
    Returns:
        pyodbc.Connection
        
    Secrets File Format:
    {
        "driver": "ODBC Driver 17 for SQL Server",
        "server": "prod-server.us.bank-dns.com,49001",
        "database": "Servicing",
        "uid": "prod_user",
        "pwd": "prod_password",
        "trusted_connection": "no",
        "encrypt": "yes"
    }
    """
    if not secrets_path:
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config", "secrets_mssql.json"
        )
    
    with open(secrets_path) as f:
        secrets = json.load(f)
    
    conn_str = (
        f"DRIVER={{{secrets['driver']}}};"
        f"SERVER={secrets['server']};"
        f"DATABASE={secrets['database']};"
        f"UID={secrets['uid']};"
        f"PWD={secrets['pwd']};"
        f"Encrypt={secrets.get('encrypt', 'yes')};"
        f"TrustServerCertificate=yes"
    )
    
    logger.info(f"Connecting to MSSQL: {secrets['server']}/{secrets['database']}")
    return pyodbc.connect(conn_str)
```

### File: `backend/db/queries.py`

```python
"""
SQL query constants for tblExternalDIDRef.

All queries use parameterized placeholders (?) for safety.
Compatible with both MySQL and MSSQL via pyodbc.
"""

# Check if a ServicerID exists in the database
CHECK_SERVICER_EXISTS = """
    SELECT DISTINCT CompanyID 
    FROM tblExternalDIDRef 
    WHERE CompanyID = ?
"""

# Get all deals for a given CompanyID (servicer)
GET_DEALS_BY_COMPANY = """
    SELECT DID, ImportDID, CompanyID 
    FROM tblExternalDIDRef 
    WHERE CompanyID = ?
    ORDER BY DID, ImportDID
"""

# Get summary stats for a CompanyID
GET_COMPANY_SUMMARY = """
    SELECT 
        COUNT(*) as total_rows,
        COUNT(DISTINCT DID) as unique_deals,
        COUNT(DISTINCT ImportDID) as unique_keywords
    FROM tblExternalDIDRef 
    WHERE CompanyID = ?
"""

# Get all distinct ServicerIDs
GET_ALL_SERVICER_IDS = """
    SELECT DISTINCT CompanyID 
    FROM tblExternalDIDRef 
    ORDER BY CompanyID
"""

# Get deals by DID name (for deal lookups)
GET_DEALS_BY_DID = """
    SELECT DID, ImportDID, CompanyID 
    FROM tblExternalDIDRef 
    WHERE DID LIKE ?
    ORDER BY CompanyID, ImportDID
"""

# Search deals by ImportDID keyword
SEARCH_BY_IMPORT_DID = """
    SELECT DID, ImportDID, CompanyID 
    FROM tblExternalDIDRef 
    WHERE ImportDID LIKE ?
    ORDER BY CompanyID, DID
"""
```

---

## Deal Repository

### File: `backend/db/deal_repo.py`

```python
"""
Data access layer for tblExternalDIDRef.

Provides typed methods for querying the deal reference table.
Uses the dual-mode connection factory, so it works transparently
against either MySQL (dev) or MSSQL (prod).

All methods return plain dicts/lists (JSON-serializable), not ORM objects.

Usage:
    repo = DealRepository(prod_mode=False, secrets_path="config/secrets_mysql.json")
    deals = repo.get_deals_by_company(150)
    exists = repo.servicer_exists(150)
    repo.close()
"""
import logging
from typing import List, Dict, Optional, Set
from .connection import get_connection
from . import queries

logger = logging.getLogger("frp.db.deals")


class DealRepository:
    """
    Data access for tblExternalDIDRef.
    
    Thread Safety: NOT thread-safe. Create one instance per operation.
    """

    def __init__(self, prod_mode: bool = False, secrets_path: Optional[str] = None):
        """
        Initialize with database connection.
        
        Args:
            prod_mode: True for MSSQL, False for MySQL
            secrets_path: Path to secrets file
        """
        self.conn = get_connection(prod_mode, secrets_path)

    def servicer_exists(self, company_id: int) -> bool:
        """
        Check if a CompanyID exists in tblExternalDIDRef.
        
        Args:
            company_id: The CompanyID (ServicerID) to check
            
        Returns:
            True if at least one row exists with this CompanyID
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.CHECK_SERVICER_EXISTS, (company_id,))
        result = cursor.fetchone()
        cursor.close()
        return result is not None

    def get_deals_by_company(self, company_id: int) -> List[Dict]:
        """
        Get all deal mappings for a CompanyID.
        
        Args:
            company_id: The CompanyID (ServicerID)
            
        Returns:
            List of dicts: [{"DID": "...", "ImportDID": "...", "CompanyID": N}, ...]
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.GET_DEALS_BY_COMPANY, (company_id,))
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return rows

    def get_company_summary(self, company_id: int) -> Dict:
        """
        Get summary statistics for a CompanyID.
        
        Returns:
            Dict: {"total_rows": N, "unique_deals": N, "unique_keywords": N}
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.GET_COMPANY_SUMMARY, (company_id,))
        row = cursor.fetchone()
        cursor.close()
        if row:
            return {
                "total_rows": row[0],
                "unique_deals": row[1],
                "unique_keywords": row[2],
            }
        return {"total_rows": 0, "unique_deals": 0, "unique_keywords": 0}

    def get_all_servicer_ids(self) -> Set[int]:
        """
        Get all distinct CompanyIDs from the database.
        
        Returns:
            Set of CompanyID integers
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.GET_ALL_SERVICER_IDS)
        ids = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return ids

    def search_by_did(self, did_pattern: str) -> List[Dict]:
        """
        Search deals by DID name pattern (LIKE query).
        
        Args:
            did_pattern: DID search pattern (e.g., "%CSFB%")
            
        Returns:
            List of matching deal dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.GET_DEALS_BY_DID, (f"%{did_pattern}%",))
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return rows

    def search_by_import_did(self, keyword: str) -> List[Dict]:
        """
        Search deals by ImportDID keyword pattern.
        
        Args:
            keyword: ImportDID search pattern (e.g., "%C88%")
            
        Returns:
            List of matching deal dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(queries.SEARCH_BY_IMPORT_DID, (f"%{keyword}%",))
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return rows

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
```

---

## Log File Parser

### File: `backend/logs/parser.py`

```python
"""
Email/SFTP monitor log file parser.

Parses log files produced by EmailMonitor.ps1 and SFTP monitor scripts.

Log Format:
    Header block (7 lines) with ## prefixes
    Then timestamped lines: "YYYY-MM-DD HH:MM:SS.mmm:\t<message>"

Key Patterns:
    Job start:      "Starting Outlook download for {JOB_NAME} ({MAILBOX})..."
    Emails found:   "found {N}"
    Processing:     "Processing: [{SUBJECT}]"
    From:           "From: {SENDER}"
    Parser match:   "Matched email [{SUBJECT}] to [{PARSER}] parser"
    File load:      " Load > {FILENAME} ({MIME_TYPE})"
    Template queue: "Queue file [{FILENAME}] for [{TEMPLATE}] template"
    DID failure:    "Did not find DID mapping for [{SUBJECT}]... Skipped..."
    Error:          Any line containing "error", "exception", "failed" (case-insensitive)
"""
import re
import logging
import os
from typing import List, Optional
from .models import LogEvent

logger = logging.getLogger("frp.logs.parser")


# Regex patterns for log line parsing
PATTERNS = {
    "timestamp": re.compile(
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}):\t(.*)$'
    ),
    "job_start": re.compile(
        r'Starting Outlook download for\s+(\S+)\s+\(([^)]+)\)'
    ),
    "found_count": re.compile(
        r'found\s+(\d+)'
    ),
    "processing": re.compile(
        r'Processing:\s+\[(.+)\]'
    ),
    "from": re.compile(
        r'From:\s+(.+)$'
    ),
    "parser_match": re.compile(
        r'Matched email\s+\[.+\]\s+to\s+\[(\w+)\]\s+parser'
    ),
    "file_load": re.compile(
        r'\s*Load\s*>\s*(.+?)\s*\('
    ),
    "template_queue": re.compile(
        r'Queue file\s+\[(.+?)\]\s+for\s+\[(.+?)\]\s+template'
    ),
    "did_mapping_failed": re.compile(
        r'Did not find DID mapping for\s+\[(.+?)\]'
    ),
    "error": re.compile(
        r'(?:error|exception|failed|cannot|unable)', re.IGNORECASE
    ),
}


class LogFileParser:
    """
    Parses a single monitor log file into structured events.
    
    Usage:
        parser = LogFileParser("email")
        events = parser.parse_file("/path/to/logfile.log")
    """

    def __init__(self, log_type: str = "email"):
        """
        Args:
            log_type: "email" or "sftp"
        """
        self.log_type = log_type

    def parse_file(self, filepath: str) -> List[LogEvent]:
        """
        Parse a single log file into a list of events.
        
        Args:
            filepath: Absolute path to log file
            
        Returns:
            List of LogEvent objects extracted from the file
            
        Implementation:
            1. Read all lines
            2. Skip header block (lines starting with ##)
            3. Track current job context (name, mailbox)
            4. For each timestamped line:
               a. Extract timestamp and message
               b. Match against patterns in priority order
               c. Create LogEvent with context
            5. Return accumulated events
            
        State Machine:
            - current_job_name: Updated on "job_start" match
            - current_mailbox: Updated on "job_start" match
            - current_subject: Updated on "processing" match
            - current_sender: Updated on "from" match  
            - These carry forward until next job_start resets context
        """
        pass

    def _extract_timestamp(self, line: str) -> Optional[tuple]:
        """
        Extract ISO timestamp and message from a log line.
        
        Args:
            line: Raw log line
            
        Returns:
            (timestamp_str, message) tuple, or None if no timestamp found
        """
        pass

    def _classify_event(self, message: str, timestamp: str, 
                         current_job: str, current_mailbox: str,
                         current_subject: str, current_sender: str,
                         filename: str) -> Optional[LogEvent]:
        """
        Classify a log message into an event type and create LogEvent.
        
        Args:
            message: The message portion of the log line (after timestamp)
            timestamp: ISO timestamp string
            current_job: Current job context
            current_mailbox: Current mailbox context
            current_subject: Current email subject context
            current_sender: Current sender context
            filename: Source log filename
            
        Returns:
            LogEvent if message matches a known pattern, None otherwise
        """
        pass
```

---

## SQLite Log Indexer

### File: `backend/logs/indexer.py`

```python
"""
SQLite-based log event indexer.

Manages the local SQLite database that stores parsed log events
for fast querying. Supports incremental sync (only processes new files)
and configurable retention.

Database Location: Configured by caller (typically workspace-local)

Usage:
    indexer = LogIndexer("/path/to/frp_logs.db")
    result = indexer.sync(log_folder="/path/to/logs", log_type="email", retention_months=3)
    events = indexer.query_events(job_name="COOFS_LateMoney", limit=20)
    indexer.close()
"""
import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .parser import LogFileParser

logger = logging.getLogger("frp.logs.indexer")


class LogIndexer:
    """
    SQLite indexer for email/SFTP monitor logs.
    """

    SCHEMA_VERSION = "1.0"

    def __init__(self, db_path: str):
        """
        Initialize indexer, creating database and tables if needed.
        
        Args:
            db_path: Absolute path to SQLite database file
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Create tables and indexes if they don't exist."""
        # See SQLite schema in System Design doc
        pass

    def sync(self, log_folder: str, log_type: str = "email",
             retention_months: int = 3) -> Dict:
        """
        Sync log files from a folder into the SQLite index.
        
        Args:
            log_folder: Path to folder containing .log files
            log_type: "email" or "sftp"
            retention_months: Months of data to retain (older events purged)
            
        Returns:
            Dict: {
                "files_processed": N,
                "events_indexed": N,
                "files_skipped": N,  (already indexed)
                "files_errored": N,
                "events_purged": N,  (retention cleanup)
                "errors": ["..."]
            }
            
        Implementation:
            1. List all .log files in folder
            2. Query indexed_files for already-processed files
            3. For each new file:
               a. Parse with LogFileParser
               b. Insert events into log_events
               c. Record in indexed_files
            4. Purge events older than retention_months
            5. Update index_metadata (last_sync, total_events)
            6. Return summary
        """
        pass

    def query_events(self, job_name: Optional[str] = None,
                     event_type: Optional[str] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     limit: int = 50) -> List[Dict]:
        """
        Query indexed log events with filters.
        
        Args:
            job_name: Filter by job name (exact match)
            event_type: Filter by event type
            start_date: ISO date string for range start
            end_date: ISO date string for range end
            limit: Maximum results to return
            
        Returns:
            List of event dicts, ordered by timestamp DESC
        """
        pass

    def get_job_summary(self, job_name: str) -> Dict:
        """
        Get summary statistics for a specific job.
        
        Returns:
            Dict: {
                "job_name": str,
                "first_seen": str (ISO timestamp),
                "last_seen": str (ISO timestamp),
                "total_events": int,
                "total_emails_processed": int,
                "total_files_loaded": int,
                "total_errors": int,
                "total_did_failures": int,
                "unique_templates": [str],
                "unique_senders": [str]
            }
        """
        pass

    def get_sync_status(self) -> Dict:
        """
        Get current index status.
        
        Returns:
            Dict: {
                "db_path": str,
                "last_sync": str or None,
                "total_events": int,
                "total_files_indexed": int,
                "schema_version": str,
                "db_size_mb": float
            }
        """
        pass

    def _is_file_indexed(self, filename: str) -> bool:
        """Check if a log file has already been indexed."""
        pass

    def _record_indexed_file(self, filename: str, event_count: int, file_size: int):
        """Record that a file has been indexed."""
        pass

    def _purge_old_events(self, retention_months: int) -> int:
        """
        Delete events older than retention_months.
        
        Returns:
            Number of events deleted
        """
        pass

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
```

---

## CLI Entry Point

### File: `cli/main.py`

```python
"""
FRP Agent CLI entry point.

All commands return JSON on stdout. Logs go to stderr.

Usage:
    python -m cli.main search_jobs --query "rptent" --settings-path "path/Settings.xml"
    python -m cli.main validate_xml --settings-path "path/Settings.xml" --db-mode mysql
    python -m cli.main sync_logs --log-folder "path/logs" --log-type email --db-path "frp_logs.db"
    python -m cli.main servicer_dossier --servicer-id 150 --settings-path "path/Settings.xml"
    python -m cli.main list_backups --settings-path "path/Settings.xml"
    python -m cli.main save_xml --settings-path "path/Settings.xml"
    python -m cli.main status
"""
import sys
import json
import argparse
import time
import logging
from backend.common.models import CliResponse

# Configure logging to stderr (stdout is for JSON only)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)


def cmd_search_jobs(args) -> CliResponse:
    """
    Search and filter jobs across Settings.xml files.
    
    Args:
        args.query: Search string
        args.xml_type: "email", "sftp", or "all"
        args.settings_path: Path to email Settings.xml
        args.sftp_settings_path: Path to SFTP Settings.xml (optional)
        
    Returns:
        CliResponse with data: { jobs: [...], total_count: N, xml_type: str }
    """
    pass


def cmd_validate_xml(args) -> CliResponse:
    """
    Validate a Settings.xml file.
    
    Args:
        args.xml_type: "email" or "sftp"
        args.settings_path: Path to Settings.xml
        args.db_mode: "mysql" or "mssql" (optional — None skips DB checks)
        args.secrets_path: Path to secrets file (optional)
        
    Returns:
        CliResponse with data: ValidationResult.to_dict()
    """
    pass


def cmd_sync_logs(args) -> CliResponse:
    """
    Sync log files into SQLite index.
    
    Args:
        args.log_folder: Path to log folder
        args.log_type: "email" or "sftp"
        args.db_path: Path to SQLite database
        args.retention_months: Months to retain
    """
    pass


def cmd_servicer_dossier(args) -> CliResponse:
    """
    Generate servicer dossier report.
    
    Args:
        args.servicer_id: CompanyID (optional)
        args.job_name: Job name (optional — alternative to servicer_id)
        args.settings_path: Email Settings.xml path
        args.sftp_settings_path: SFTP Settings.xml path (optional)
        args.db_mode: "mysql" or "mssql"
        args.secrets_path: Secrets file path
        args.log_db_path: SQLite database path
    """
    pass


def cmd_list_backups(args) -> CliResponse:
    """
    List backup files for a Settings.xml.
    
    Args:
        args.settings_path: Path to Settings.xml
        args.xml_type: "email" or "sftp"
    """
    pass


def cmd_save_xml(args) -> CliResponse:
    """
    Save Settings.xml with backup.
    
    Args:
        args.settings_path: Path to Settings.xml
        args.xml_type: "email" or "sftp"
    """
    pass


def cmd_status(args) -> CliResponse:
    """
    Return agent status information.
    
    Returns:
        CliResponse with version, settings summary, index status
    """
    pass


def main():
    parser = argparse.ArgumentParser(prog="frp-agent")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # search_jobs
    sp = sub.add_parser("search_jobs", help="Search and filter jobs")
    sp.add_argument("--query", required=True, help="Search query string")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"])
    sp.add_argument("--settings-path", required=True, help="Email Settings.xml path")
    sp.add_argument("--sftp-settings-path", default=None, help="SFTP Settings.xml path")

    # validate_xml
    vp = sub.add_parser("validate_xml", help="Validate Settings.xml")
    vp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    vp.add_argument("--settings-path", required=True)
    vp.add_argument("--db-mode", default=None, choices=["mysql", "mssql"])
    vp.add_argument("--secrets-path", default=None)

    # sync_logs
    lp = sub.add_parser("sync_logs", help="Sync logs into SQLite")
    lp.add_argument("--log-folder", required=True)
    lp.add_argument("--log-type", default="email", choices=["email", "sftp"])
    lp.add_argument("--db-path", required=True)
    lp.add_argument("--retention-months", type=int, default=3)

    # servicer_dossier
    dp = sub.add_parser("servicer_dossier", help="Generate servicer dossier")
    dp.add_argument("--servicer-id", type=int, default=None)
    dp.add_argument("--job-name", default=None)
    dp.add_argument("--settings-path", required=True)
    dp.add_argument("--sftp-settings-path", default=None)
    dp.add_argument("--db-mode", default="mysql", choices=["mysql", "mssql"])
    dp.add_argument("--secrets-path", default=None)
    dp.add_argument("--log-db-path", default=None)

    # list_backups
    bp = sub.add_parser("list_backups", help="List backup files")
    bp.add_argument("--settings-path", required=True)
    bp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # save_xml
    xp = sub.add_parser("save_xml", help="Save Settings.xml with backup")
    xp.add_argument("--settings-path", required=True)
    xp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # status
    sub.add_parser("status", help="Agent status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Command dispatch
    handlers = {
        "search_jobs": cmd_search_jobs,
        "validate_xml": cmd_validate_xml,
        "sync_logs": cmd_sync_logs,
        "servicer_dossier": cmd_servicer_dossier,
        "list_backups": cmd_list_backups,
        "save_xml": cmd_save_xml,
        "status": cmd_status,
    }

    start = time.time()
    try:
        response = handlers[args.command](args)
        response.elapsed_ms = round((time.time() - start) * 1000, 1)
    except Exception as e:
        logging.getLogger("frp.cli").exception(f"Command {args.command} failed")
        response = CliResponse(
            success=False,
            command=args.command,
            errors=[str(e)],
            elapsed_ms=round((time.time() - start) * 1000, 1),
        )

    # JSON to stdout ONLY
    json.dump(response.to_dict(), sys.stdout, default=str)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
```

---

## Extension JavaScript Contracts

### File: `extension/copilot/tool.js`

```javascript
/**
 * Backend bridge — calls Python CLI and parses JSON response.
 * 
 * Design: All backend calls go through this single function.
 * The extension never talks to Python except via runCliJson().
 * 
 * @param {string} command - CLI command name (e.g., 'search_jobs')
 * @param {object} params - Command parameters as key-value pairs
 * @param {object} shared - Shared extension context (outputChannel, etc.)
 * @returns {Promise<object>} Parsed JSON response from backend
 */
async function backendCall(command, params, shared) {
    // Build args array from params: { query: "text", xmlType: "email" }
    // → ['search_jobs', '--query', 'text', '--xml-type', 'email']
    
    // Map JS camelCase keys to CLI kebab-case: xmlType → --xml-type
    // Map settings paths from VS Code config:
    //   frpAgent.outlookSettingsPath → --settings-path
    //   frpAgent.sftpSettingsPath → --sftp-settings-path
    //   frpAgent.prod → --db-mode mysql or mssql
    
    // Call runCliJson() from frp_backend.js
    // Parse response envelope
    // Log to output channel if verbose
    // Return response.data (unwrap envelope)
}
```

### File: `extension/lib/frp_backend.js`

```javascript
/**
 * Backend runner factory — ExeRunner or VenvRunner.
 * 
 * Same pattern as KTS: 
 * - Dev mode (venv): python -m cli.main <command>
 * - Prod mode (exe): frp-backend.exe <command>
 * 
 * Selected by frpAgent.backendMode setting: auto | venv | exe
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let runner = null;

class ExeRunner {
    constructor(exePath) { this.exePath = exePath; }
    spawn(args, opts) { return spawn(this.exePath, args, opts); }
}

class VenvRunner {
    constructor(pythonPath, cliModule) {
        this.pythonPath = pythonPath;
        this.cliModule = cliModule;
    }
    spawn(args, opts) {
        return spawn(this.pythonPath, ['-m', this.cliModule, ...args], opts);
    }
}

async function initBackendRunner(vscode, context, outputChannel) {
    const config = vscode.workspace.getConfiguration('frpAgent');
    const mode = config.get('backendMode') || 'auto';
    
    if (mode === 'exe' || mode === 'auto') {
        const exePath = path.join(context.extensionPath, 'bin', 'win-x64', 
                                   'frp-backend', 'frp-backend.exe');
        if (fs.existsSync(exePath)) {
            runner = new ExeRunner(exePath);
            outputChannel.appendLine('[FRP] Using compiled backend (exe)');
            return;
        }
    }
    
    // Fallback to venv
    runner = new VenvRunner('python', 'cli.main');
    outputChannel.appendLine('[FRP] Using Python venv backend');
}

async function runCliJson(args, env = {}) {
    return new Promise((resolve, reject) => {
        const proc = runner.spawn(args, { 
            env: { ...process.env, ...env },
            cwd: env.WORKSPACE_ROOT || process.cwd()
        });
        let stdout = '';
        let stderr = '';
        
        proc.stdout.on('data', d => stdout += d.toString());
        proc.stderr.on('data', d => stderr += d.toString());
        
        proc.on('close', code => {
            if (code !== 0) {
                return reject(new Error(`Backend exited ${code}: ${stderr.slice(-500)}`));
            }
            try {
                resolve(JSON.parse(stdout));
            } catch (err) {
                reject(new Error(`Invalid JSON from backend: ${err.message}\nOutput: ${stdout.slice(0, 200)}`));
            }
        });
    });
}

module.exports = { initBackendRunner, runCliJson };
```

---

## Chat Participant Handler

### File: `extension/chat/participant.js`

```javascript
/**
 * @frp Chat Participant — main handler.
 * 
 * Slash Commands:
 *   /jobs    → J-01 (search), J-05 (validate)
 *   /deals   → D-04 (servicer dossier)
 *   /logs    → L-01 (sync)
 *   /deploy  → X-01 (save), X-04 (list backups)
 *   /triage  → (Phase 3)
 *   /analyze → (Phase 4)
 * 
 * Handler Flow:
 *   1. Extract command and prompt from request
 *   2. Parse subcommand from prompt (e.g., "sync", "validate", "save email")
 *   3. Call backend via tool.js
 *   4. Select LLM model
 *   5. Build context + question for LLM
 *   6. Stream LLM response to chat
 *   7. Generate follow-up suggestions
 */

const SYSTEM_PROMPT = `You are FRP Agent — a precise operations assistant for the File Reception Portal.
You help manage email and SFTP monitoring jobs, analyze deal coverage, query application logs, and triage emails.

Rules:
- Answer using ONLY the data provided in the context below.
- Format job listings as markdown tables when showing multiple jobs.
- Format validation results with clear error/warning/info icons.
- When showing deal mappings, include DID, ImportDID, and CompanyID columns.
- For log summaries, show timestamps, job names, and event counts.
- If the data doesn't contain an answer, say so explicitly.
- Never invent job configurations, deal mappings, or log events.
- Use professional, concise language appropriate for financial operations.`;

// Slash command → subcommand routing
const COMMAND_HANDLERS = {
    'jobs': {
        // Default: search. Subcommands: validate, validate sftp
        defaultAction: 'search',
        subcommands: {
            'validate': { action: 'validate_xml', xmlType: 'email' },
            'validate sftp': { action: 'validate_xml', xmlType: 'sftp' },
            'validate email': { action: 'validate_xml', xmlType: 'email' },
        }
    },
    'deals': {
        // Default: search by query. Subcommands: servicer <id>
        defaultAction: 'search_deals',
        subcommands: {
            'servicer': { action: 'servicer_dossier' },
        }
    },
    'logs': {
        // Default: query. Subcommands: sync
        defaultAction: 'query_logs',
        subcommands: {
            'sync': { action: 'sync_logs' },
        }
    },
    'deploy': {
        // Subcommands: save email, save sftp, backups, backups sftp
        defaultAction: 'list_backups',
        subcommands: {
            'save email': { action: 'save_xml', xmlType: 'email' },
            'save sftp': { action: 'save_xml', xmlType: 'sftp' },
            'backups': { action: 'list_backups', xmlType: 'email' },
            'backups sftp': { action: 'list_backups', xmlType: 'sftp' },
            'backups email': { action: 'list_backups', xmlType: 'email' },
        }
    },
};

// Model selection: request.model → setting → auto-detect
// (Same as KTS bootstrap pattern — see §7)

// LLM generation: embed SYSTEM_PROMPT in User message
// (Same as KTS bootstrap pattern — see §7)
// CRITICAL: LanguageModelChatMessage.User() only — NO .System()

// Follow-up suggestions (deterministic, zero LLM cost):
// After /jobs search → suggest "validate", "servicer <id>"
// After /logs sync → suggest "what happened today?"
// After /deals servicer → suggest "validate", "show logs for <job>"
```

---

## Configuration

### File: `config/settings.py`

```python
"""
Backend configuration management.

Reads configuration from environment variables passed by the VS Code extension.
The extension reads VSIX settings and passes them as env vars or CLI args.
"""
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class FrpConfig:
    """
    Backend configuration.
    
    Resolution order:
    1. CLI arguments (highest priority)
    2. Environment variables
    3. Defaults
    """
    prod_mode: bool = False
    outlook_settings_path: str = ""
    sftp_settings_path: str = ""
    email_log_folder: str = ""
    sftp_log_folder: str = ""
    log_retention_months: int = 3
    log_level: str = "normal"
    secrets_path: Optional[str] = None
    log_db_path: str = "frp_logs.db"

    @classmethod
    def from_env(cls) -> 'FrpConfig':
        """Load config from environment variables."""
        return cls(
            prod_mode=os.environ.get("FRP_PROD", "false").lower() == "true",
            outlook_settings_path=os.environ.get("FRP_OUTLOOK_SETTINGS", ""),
            sftp_settings_path=os.environ.get("FRP_SFTP_SETTINGS", ""),
            email_log_folder=os.environ.get("FRP_EMAIL_LOG_FOLDER", ""),
            sftp_log_folder=os.environ.get("FRP_SFTP_LOG_FOLDER", ""),
            log_retention_months=int(os.environ.get("FRP_LOG_RETENTION", "3")),
            log_level=os.environ.get("FRP_LOG_LEVEL", "normal"),
            log_db_path=os.environ.get("FRP_LOG_DB_PATH", "frp_logs.db"),
        )
```

---

## Error Handling Strategy

### Python Backend Errors

| Error Category | Handling | User Message |
|----------------|----------|-------------|
| FileNotFoundError (XML) | CliResponse.success=False, error in errors[] | "Settings.xml not found at: <path>. Check frpAgent.outlookSettingsPath setting." |
| ET.ParseError (malformed XML) | CliResponse.success=False | "Settings.xml is malformed XML: <detail>. Check the file manually." |
| pyodbc.Error (DB connection) | CliResponse.success=False | "Database connection failed: <detail>. Check frpAgent.prod setting and secrets file." |
| pyodbc.Error (query) | CliResponse.success=False | "Database query failed: <detail>." |
| sqlite3.Error | CliResponse.success=False | "Log index error: <detail>. Try deleting frp_logs.db and re-syncing." |
| PermissionError (backup) | CliResponse.success=False | "Cannot write backup: <detail>. Check folder permissions." |
| Generic Exception | CliResponse.success=False, logged to stderr | "Unexpected error: <detail>. Check FRP Agent output panel for details." |

### JavaScript Extension Errors

| Error Category | Handling | User Message |
|----------------|----------|-------------|
| Backend not started | Show error notification | "FRP backend not available. Check Python installation." |
| Backend crash (exit code ≠ 0) | Log stderr, show in chat | "Backend error: <detail>" |
| Invalid JSON from backend | Log raw output | "Backend returned invalid response. Check FRP Agent output panel." |
| LLM unavailable | Fallback to raw data formatting | Show raw backend data without LLM formatting |
| LLM quota exceeded | Fallback to raw data | Same as above |
| Missing VSIX settings | Show warning + link to settings | "Please configure frpAgent.outlookSettingsPath in VS Code settings." |

### Graceful Degradation Priorities

1. **DB unavailable** → All UCs still work except J-05 cross-reference and D-04 deal mappings. Show warning.
2. **SQLite unavailable** → L-01 reports error. D-04 skips log section. Other UCs work.
3. **LLM unavailable** → Raw data returned as formatted markdown (no natural language framing).
4. **SFTP Settings path not set** → Email UCs work fine. SFTP commands show "SFTP settings path not configured."
