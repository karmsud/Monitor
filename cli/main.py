"""FRP Agent CLI — command-line entry point.

All commands emit JSON on stdout.  Logs go to stderr so that callers
can reliably pipe / parse the JSON output without log noise.

Usage::

    python -m cli.main search_jobs --query "acme" --settings-path Settings.xml
    python -m cli.main status
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

# ── project imports ──────────────────────────────────────────────────── #
from backend.common.models import CliResponse
from backend.xml.parser import SettingsXmlParser
from backend.xml.writer import XmlWriter
from backend.backup.manager import BackupManager
from backend.logs.indexer import LogIndexer
from backend.db.deal_repo import DealRepository

# ── constants ────────────────────────────────────────────────────────── #
__version__ = "1.0.0"

logger = logging.getLogger("frp.cli")


# ===================================================================== #
#  Logging bootstrap (stderr only)
# ===================================================================== #

def _configure_logging() -> None:
    """Send all log output to *stderr* so stdout remains clean JSON."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


# ===================================================================== #
#  Helpers
# ===================================================================== #

def _repo_from_args(args) -> DealRepository:
    """Build a :class:`DealRepository` from parsed CLI arguments."""
    db_mode = getattr(args, "db_mode", "mysql") or "mysql"
    return DealRepository(
        prod_mode=db_mode.lower() == "mssql",
        secrets_path=getattr(args, "secrets_path", None),
        mssql_server=getattr(args, "mssql_server", None),
        mssql_database=getattr(args, "mssql_database", None),
    )


def _ts_repo_from_args(args):
    """Build a :class:`TemplateStagingRepository` from parsed CLI arguments."""
    from backend.db.template_staging_repo import TemplateStagingRepository

    db_mode = getattr(args, "db_mode", "mysql") or "mysql"
    return TemplateStagingRepository(
        prod_mode=db_mode.lower() == "mssql",
        secrets_path=getattr(args, "secrets_path", None),
        mssql_server=getattr(args, "mssql_server", None),
        mssql_database=getattr(args, "mssql_database", None),
    )


def _xml_index_from_args(args):
    """Build an :class:`XmlJobIndex` if a cache DB path is available.

    If the DB file exists it is opened directly.  If it does *not* yet
    exist but the XML settings files are available, the cache is created
    and populated automatically so the caller always gets a usable index.
    """
    from backend.db.xml_index import XmlJobIndex

    db_path = getattr(args, "cache_db_path", None)
    if not db_path:
        return None

    needs_rebuild = not os.path.exists(db_path)
    index = XmlJobIndex(db_path)

    if not needs_rebuild:
        # Quick check: if tables exist but are empty, treat as needing rebuild
        try:
            cur = index._conn.execute(
                "SELECT COUNT(*) FROM email_jobs UNION ALL SELECT COUNT(*) FROM sftp_jobs"
            )
            counts = [r[0] for r in cur.fetchall()]
            if sum(counts) == 0:
                needs_rebuild = True
        except Exception:
            needs_rebuild = True

    if needs_rebuild:
        logger.info("Cache DB empty or missing — auto-rebuilding from XML settings")
        xml_type = getattr(args, "xml_type", "all")
        try:
            settings_path = getattr(args, "settings_path", None)
            if settings_path and xml_type in ("email", "all"):
                index.rebuild(settings_path, "email")
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path and xml_type in ("sftp", "all"):
                index.rebuild(sftp_path, "sftp")
        except Exception as exc:
            logger.warning("Auto-rebuild failed (non-fatal): %s", exc)

    return index


def _normalise_staging_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text == "(none)":
        return ""
    return text.lower()


def _collect_staging_config_jobs(args) -> List[Dict]:
    """Load job summaries from configured XML files for staging correlation."""
    jobs: List[Dict] = []
    xml_type = getattr(args, "xml_type", "all") or "all"

    settings_path = getattr(args, "settings_path", None)
    if settings_path and xml_type in ("email", "all"):
        parser = SettingsXmlParser(settings_path)
        for job in parser.get_all_jobs():
            summary = job.to_summary_dict()
            summary["xml_type"] = "email"
            jobs.append(summary)

    sftp_path = getattr(args, "sftp_settings_path", None)
    if sftp_path and xml_type in ("sftp", "all"):
        parser = SettingsXmlParser(sftp_path)
        for job in parser.get_all_jobs():
            summary = job.to_summary_dict()
            summary["xml_type"] = "sftp"
            jobs.append(summary)

    return jobs


def _collect_staging_cached_jobs(args) -> List[Dict]:
    """Load cached job summaries from the SQLite XML index when available."""
    index = _xml_index_from_args(args)
    if not index:
        return []

    try:
        return index.get_all_jobs("all")
    finally:
        index.close()


def _match_jobs_by_scrubber(jobs: List[Dict], template_name: str) -> List[Dict]:
    """Return jobs whose scrubber/template matches *template_name*."""
    target = _normalise_staging_text(template_name)
    if not target:
        return []

    exact = []
    partial = []
    for job in jobs:
        scrubber = _normalise_staging_text(job.get("scrubber") or job.get("template"))
        if not scrubber:
            continue
        if scrubber == target:
            exact.append(job)
        elif target in scrubber or scrubber in target:
            partial.append(job)

    return exact or partial


def _classify_staging_source(record: Dict) -> str:
    data_source = str(record.get("DataSource") or "").strip()
    source_process = str(record.get("SourceProcess") or "").strip()

    if "SFTPMonitor:" in data_source:
        return "sftp"
    if "Queued via macro" in data_source or source_process == "ManualQueue":
        return "manual"
    if data_source:
        return "email"
    return "unknown"


def _classify_staging_state(record: Dict) -> str:
    start_time = record.get("StartTime")
    end_time = record.get("EndTime")
    result_code = record.get("ResultCode")

    if not start_time and not end_time and result_code in (None, "", "null"):
        return "queued"
    if start_time and not end_time:
        return "running"
    if result_code == 0:
        return "success"
    if result_code == 1:
        return "failed"
    if end_time:
        return "completed"
    return "unknown"


def _summarise_staging_record(record: Dict) -> Dict:
    summary = dict(record)
    summary["source_type"] = _classify_staging_source(record)
    summary["processing_state"] = _classify_staging_state(record)
    return summary


def _extract_filepath_token(filepath: str) -> str:
    cleaned = str(filepath or "").strip().rstrip("\\/")
    if not cleaned:
        return ""
    parts = re.split(r"[\\/]", cleaned)
    return parts[-1] if parts else cleaned


def _normalise_path_for_compare(path_text: str) -> str:
    return str(path_text or "").strip().lower().replace("\\", "/")


def _filepath_matches_save_path(filepath: str, save_path: str) -> bool:
    file_norm = _normalise_path_for_compare(filepath)
    save_norm = _normalise_path_for_compare(save_path)
    if not file_norm or not save_norm:
        return False

    token_stripped = save_norm
    for token in ("{dealfolder}", "{yyyy}", "{yy}", "{m}", "{mm}", "{d}", "{dd}"):
        token_stripped = token_stripped.replace(token, "")
    token_stripped = token_stripped.replace("//", "/").rstrip("/")
    return file_norm.startswith(save_norm.rstrip("/")) or (token_stripped and token_stripped in file_norm)


def _record_matches_job_origin(record: Dict, job: Dict) -> bool:
    source_type = _classify_staging_source(record)
    data_source = str(record.get("DataSource") or "")

    if source_type == "manual":
        return True

    if source_type == "sftp":
        job_path = job.get("sftp_path") or job.get("path") or ""
        return bool(job_path) and _normalise_path_for_compare(job_path) in _normalise_path_for_compare(data_source)

    if source_type == "email":
        mailbox = str(job.get("mailbox") or "").strip().lower()
        return bool(mailbox) and mailbox in data_source.lower()

    return False


def _build_staging_jobs_context(matching_jobs: List[Dict]) -> Dict:
    email_jobs = [job for job in matching_jobs if (job.get("xml_type") or "email") == "email"]
    sftp_jobs = [job for job in matching_jobs if (job.get("xml_type") or "") == "sftp"]
    return {
        "all_jobs": matching_jobs,
        "email_jobs": email_jobs,
        "sftp_jobs": sftp_jobs,
        "job_count": len(matching_jobs),
    }


def _collect_staging_reference_jobs(args) -> tuple[List[Dict], str]:
    """Return reference jobs plus the source used for correlation."""
    jobs: List[Dict] = []
    source = "none"

    try:
        jobs = _collect_staging_config_jobs(args)
        if jobs:
            source = "xml"
    except Exception as exc:
        logger.warning("Unable to load staging XML jobs: %s", exc)

    if not jobs:
        try:
            jobs = _collect_staging_cached_jobs(args)
            if jobs:
                source = "sqlite"
        except Exception as exc:
            logger.warning("Unable to load staging cached jobs: %s", exc)

    deduped: List[Dict] = []
    seen = set()
    for job in jobs:
        job_name = _normalise_staging_text(job.get("job_name") or job.get("name"))
        xml_type = _normalise_staging_text(job.get("xml_type") or "email") or "email"
        key = (xml_type, job_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)

    return deduped, source


def _normalise_staging_filters(raw_filters: object) -> List[Dict[str, str]]:
    """Accept either a JSON object or list and normalise to [{field, value}]."""
    if raw_filters is None:
        return []

    payload = raw_filters
    if isinstance(raw_filters, str):
        payload = json.loads(raw_filters)

    if isinstance(payload, dict):
        return [
            {"field": str(key), "value": "" if value is None else str(value)}
            for key, value in payload.items()
            if str(key).strip() and value not in (None, "")
        ]

    if isinstance(payload, list):
        filters: List[Dict[str, str]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            field_name = str(entry.get("field") or entry.get("type") or "").strip()
            value = str(entry.get("value") or entry.get("query") or "").strip()
            if field_name and value:
                filters.append({"field": field_name, "value": value})
        return filters

    raise ValueError("--filters must be a JSON object or array of {field,value} filters.")


def _filter_staging_rows_by_days(rows: List[Dict], days: Optional[int]) -> List[Dict]:
    if days is None:
        return rows

    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=int(days))
    filtered: List[Dict] = []
    for row in rows:
        dt_value = str(row.get("Dt") or "").strip()
        if not dt_value:
            continue
        try:
            if datetime.strptime(dt_value[:10], "%Y-%m-%d") >= cutoff:
                filtered.append(row)
        except ValueError:
            filtered.append(row)
    return filtered


def _match_staging_jobs_for_record(reference_jobs: List[Dict], record: Dict) -> List[Dict]:
    template_name = record.get("TemplateName") or ""
    candidate_jobs = _match_jobs_by_scrubber(reference_jobs, template_name)
    if not candidate_jobs:
        return []

    matched = []
    for job in candidate_jobs:
        save_path = job.get("save_path") or job.get("save_location") or ""
        filepath = record.get("FilePath") or ""
        if _record_matches_job_origin(record, job) or _filepath_matches_save_path(filepath, save_path):
            matched.append(job)

    return matched or candidate_jobs


def _build_staging_summary(rows: List[Dict]) -> Dict:
    source_counts: Dict[str, int] = {}
    state_counts: Dict[str, int] = {}
    templates = set()
    dids = set()
    servicers = set()

    for row in rows:
        source = row.get("source_type") or _classify_staging_source(row)
        state = row.get("processing_state") or _classify_staging_state(row)
        source_counts[source] = source_counts.get(source, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1

        template_name = row.get("TemplateName")
        if template_name:
            templates.add(template_name)
        did = row.get("DID")
        if did:
            dids.add(did)
        servicer_id = row.get("ServicerID")
        if servicer_id not in (None, ""):
            servicers.add(servicer_id)

    return {
        "total_rows": len(rows),
        "unique_templates": len(templates),
        "unique_dids": len(dids),
        "unique_servicers": len(servicers),
        "by_source": source_counts,
        "by_state": state_counts,
    }


def _dedupe_deal_rows(rows: List[Dict]) -> List[Dict]:
    deduped: List[Dict] = []
    seen = set()
    for row in rows:
        key = (
            row.get("DID") or row.get("did"),
            row.get("ImportDID") or row.get("import_did"),
            row.get("CompanyID") or row.get("company_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


_LOG_FILTER_ALIASES = {
    "job": "job_name",
    "jobname": "job_name",
    "name": "job_name",
    "event": "event_type",
    "eventtype": "event_type",
    "type": "event_type",
    "sender": "sender",
    "mailbox": "mailbox",
    "parser": "parser",
    "filename": "filename",
    "file": "filename",
    "subject": "subject",
    "template": "template",
    "scrubber": "template",
    "log": "log_type",
    "logtype": "log_type",
}


def _normalise_log_filters(raw_filters: object) -> List[Dict[str, str]]:
    """Accept either a JSON object or list and normalise to [{field, value}]."""
    if raw_filters is None:
        return []

    payload = raw_filters
    if isinstance(raw_filters, str):
        payload = json.loads(raw_filters)

    if isinstance(payload, dict):
        filters: List[Dict[str, str]] = []
        for key, value in payload.items():
            normalized = _LOG_FILTER_ALIASES.get(str(key).strip().lower())
            if normalized and value not in (None, ""):
                filters.append({"field": normalized, "value": str(value)})
        return filters

    if isinstance(payload, list):
        filters: List[Dict[str, str]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            raw_field = str(entry.get("field") or entry.get("type") or "").strip().lower()
            normalized = _LOG_FILTER_ALIASES.get(raw_field)
            value = str(entry.get("value") or entry.get("query") or "").strip()
            if normalized and value:
                filters.append({"field": normalized, "value": value})
        return filters

    raise ValueError("--filters must be a JSON object or array of {field,value} filters.")


def _normalise_log_start(value: Optional[str], days: Optional[int]) -> Optional[str]:
    if value:
        text = str(value).strip()
        return f"{text} 00:00:00" if len(text) == 10 else text
    if days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")


def _normalise_log_end(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    return f"{text} 23:59:59" if len(text) == 10 else text


def _filter_log_events_by_mode(events: List[Dict], mode: str) -> List[Dict]:
    normalized = str(mode or "events").strip().lower()
    if normalized == "errors":
        return [
            event for event in events
            if "error" in str(event.get("event_type") or "").lower()
            or "fail" in str(event.get("event_type") or "").lower()
        ]
    if normalized == "activity":
        return [
            event for event in events
            if str(event.get("event_type") or "").lower() not in ("job_start", "job_complete", "found_count", "info")
        ]
    return events


def _group_log_events_by_email(events: List[Dict], limit: int = 20) -> List[Dict]:
    grouped: Dict[str, Dict] = {}

    for event in events:
        event_type = str(event.get("event_type") or "").lower()
        email_event_id = str(event.get("email_event_id") or "").strip()
        if not email_event_id and event_type in ("job_start", "job_complete", "found_count"):
            continue

        if not email_event_id:
            subject = str(event.get("subject") or "").strip()
            if not subject:
                continue
            email_event_id = "legacy::{job}::{mailbox}::{subject}::{sender}".format(
                job=str(event.get("job_name") or "").strip(),
                mailbox=str(event.get("mailbox") or "").strip(),
                subject=subject,
                sender=str(event.get("sender") or "").strip(),
            )

        entry = grouped.setdefault(email_event_id, {
            "email_event_id": email_event_id,
            "email_event_index": event.get("email_event_index"),
            "job_name": event.get("job_name"),
            "mailbox": event.get("mailbox"),
            "subject": event.get("subject"),
            "sender": event.get("sender"),
            "first_seen": event.get("timestamp"),
            "last_seen": event.get("timestamp"),
            "pipeline_event_count": 0,
            "info_event_count": 0,
            "error_count": 0,
            "files": set(),
            "templates": set(),
            "parsers": set(),
            "event_types": {},
        })

        entry["pipeline_event_count"] += 1
        entry["event_types"][event_type or "unknown"] = entry["event_types"].get(event_type or "unknown", 0) + 1
        if event_type == "info":
            entry["info_event_count"] += 1
        if "error" in event_type or "fail" in event_type:
            entry["error_count"] += 1

        if event.get("timestamp") and str(event.get("timestamp")) < str(entry["first_seen"]):
            entry["first_seen"] = event.get("timestamp")
        if event.get("timestamp") and str(event.get("timestamp")) > str(entry["last_seen"]):
            entry["last_seen"] = event.get("timestamp")

        if not entry.get("subject") and event.get("subject"):
            entry["subject"] = event.get("subject")
        if not entry.get("sender") and event.get("sender"):
            entry["sender"] = event.get("sender")
        if not entry.get("mailbox") and event.get("mailbox"):
            entry["mailbox"] = event.get("mailbox")
        if entry.get("email_event_index") is None and event.get("email_event_index") is not None:
            entry["email_event_index"] = event.get("email_event_index")

        if event.get("filename"):
            entry["files"].add(str(event.get("filename")))
        if event.get("template"):
            entry["templates"].add(str(event.get("template")))
        if event.get("parser"):
            entry["parsers"].add(str(event.get("parser")))

    summaries = []
    for entry in grouped.values():
        summaries.append({
            "email_event_id": entry["email_event_id"],
            "email_event_index": entry["email_event_index"],
            "job_name": entry["job_name"],
            "mailbox": entry["mailbox"],
            "subject": entry["subject"],
            "sender": entry["sender"],
            "first_seen": entry["first_seen"],
            "last_seen": entry["last_seen"],
            "pipeline_event_count": entry["pipeline_event_count"],
            "info_event_count": entry["info_event_count"],
            "error_count": entry["error_count"],
            "files": sorted(entry["files"]),
            "templates": sorted(entry["templates"]),
            "parsers": sorted(entry["parsers"]),
            "event_types": entry["event_types"],
        })

    summaries.sort(key=lambda row: (str(row.get("last_seen") or ""), row.get("pipeline_event_count") or 0), reverse=True)
    return summaries[:limit]


def _summarise_log_events(events: List[Dict], limit: int = 20) -> List[Dict]:
    grouped: Dict[str, Dict] = {}
    for event in events:
        job_name = str(event.get("job_name") or "(unknown)").strip() or "(unknown)"
        entry = grouped.setdefault(job_name, {
            "job_name": job_name,
            "first_seen": event.get("timestamp"),
            "last_seen": event.get("timestamp"),
            "total_events": 0,
            "total_files_loaded": 0,
            "total_errors": 0,
            "unique_senders": set(),
            "unique_parsers": set(),
            "mailboxes": set(),
            "event_types": {},
        })
        entry["total_events"] += 1
        event_type = str(event.get("event_type") or "")
        if event_type in ("file_load", "file_loaded"):
            entry["total_files_loaded"] += 1
        if "error" in event_type.lower() or "fail" in event_type.lower():
            entry["total_errors"] += 1
        sender = event.get("sender")
        if sender:
            entry["unique_senders"].add(sender)
        parser = event.get("parser")
        if parser:
            entry["unique_parsers"].add(parser)
        mailbox = event.get("mailbox")
        if mailbox:
            entry["mailboxes"].add(mailbox)
        entry["event_types"][event_type] = entry["event_types"].get(event_type, 0) + 1
        if event.get("timestamp") and str(event.get("timestamp")) < str(entry["first_seen"]):
            entry["first_seen"] = event.get("timestamp")
        if event.get("timestamp") and str(event.get("timestamp")) > str(entry["last_seen"]):
            entry["last_seen"] = event.get("timestamp")

    summaries = []
    for entry in grouped.values():
        summaries.append({
            "job_name": entry["job_name"],
            "first_seen": entry["first_seen"],
            "last_seen": entry["last_seen"],
            "total_events": entry["total_events"],
            "total_files_loaded": entry["total_files_loaded"],
            "total_errors": entry["total_errors"],
            "unique_senders": len(entry["unique_senders"]),
            "unique_parsers": len(entry["unique_parsers"]),
            "mailboxes": sorted(entry["mailboxes"]),
            "event_types": entry["event_types"],
        })

    summaries.sort(key=lambda row: (str(row.get("last_seen") or ""), row.get("total_events") or 0), reverse=True)
    return summaries[:limit]


def _build_log_event_summary(events: List[Dict]) -> Dict:
    by_type: Dict[str, int] = {}
    jobs = set()
    senders = set()
    parsers = set()
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        by_type[event_type] = by_type.get(event_type, 0) + 1
        if event.get("job_name"):
            jobs.add(event["job_name"])
        if event.get("sender"):
            senders.add(event["sender"])
        if event.get("parser"):
            parsers.add(event["parser"])
    return {
        "total_events": len(events),
        "unique_jobs": len(jobs),
        "unique_senders": len(senders),
        "unique_parsers": len(parsers),
        "by_event_type": by_type,
    }


def _match_log_reference_jobs(reference_jobs: List[Dict], job_names: List[str], query: str) -> List[Dict]:
    exact: List[Dict] = []
    partial: List[Dict] = []
    seen = set()
    lowered_names = {str(name or "").strip().lower() for name in job_names if str(name or "").strip()}
    lowered_query = str(query or "").strip().lower()

    for job in reference_jobs:
        job_name = str(job.get("job_name") or job.get("name") or "").strip()
        if not job_name:
            continue
        normalized = job_name.lower()
        key = ((job.get("xml_type") or "email"), normalized)
        if key in seen:
            continue
        if normalized in lowered_names:
            seen.add(key)
            exact.append(job)
            continue
        if lowered_query and (lowered_query in normalized or normalized in lowered_query):
            seen.add(key)
            partial.append(job)

    return exact or partial


def _rebuild_sqlite(args) -> None:
    """Rebuild the SQLite cache after an XML write operation.

    Called after create_job, edit_job, and rollback to keep cache in sync.
    Failures are logged but do not block the CLI response.
    """
    from backend.db.xml_index import XmlJobIndex

    db_path = getattr(args, "cache_db_path", None)
    if not db_path:
        return
    try:
        with XmlJobIndex(db_path) as index:
            xml_type = getattr(args, "xml_type", "email")
            if xml_type in ("email", "all"):
                index.rebuild(args.settings_path, "email")
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path and xml_type in ("sftp", "all"):
                index.rebuild(sftp_path, "sftp")
    except Exception as exc:
        logger.warning("SQLite rebuild failed (non-fatal): %s", exc)


def _parse_deal_lookup_filters(raw_filters: str | None) -> List[Dict[str, str]]:
    """Parse and validate ``--filters-json`` for deterministic deal lookups."""
    if not raw_filters:
        return []

    try:
        payload = json.loads(raw_filters)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --filters-json payload: {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError("--filters-json must be a JSON array of {type, value} objects.")

    filters: List[Dict[str, str]] = []
    seen = set()
    allowed = {"did", "keyword", "company", "servicer"}

    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("Each deal filter must be an object with 'type' and 'value'.")

        lookup_type = str(entry.get("type") or "").strip().lower()
        value = str(entry.get("value") or "").strip()
        if lookup_type not in allowed:
            raise ValueError(f"Unsupported deal filter type: {lookup_type or '(empty)'}")
        if not value:
            raise ValueError(f"Deal filter '{lookup_type}' requires a non-empty value.")

        canonical = "company" if lookup_type in ("company", "servicer") else lookup_type
        if canonical in seen:
            raise ValueError(f"Duplicate deal filter type: {lookup_type}")

        seen.add(canonical)
        filters.append({"type": lookup_type, "value": value})

    return filters


# ===================================================================== #
#  Command handlers
# ===================================================================== #

def cmd_search_jobs(args: argparse.Namespace) -> CliResponse:
    """Search for jobs across email and/or SFTP XML settings."""
    response = CliResponse(success=True, command="search_jobs")

    # ── Try SQLite cache first ──────────────────────────────────── #
    index = _xml_index_from_args(args)
    if index:
        try:
            all_jobs_dicts = index.search_jobs(args.query, args.xml_type)

            # Staleness check (non-blocking)
            if args.xml_type in ("email", "all"):
                try:
                    hash_result = index.check_hash(args.settings_path, "email")
                    if not hash_result["is_fresh"]:
                        response.add_warning(
                            "Cache may be stale — email config hash mismatch. "
                            "Run 'frp xml rebuild-db' to refresh."
                        )
                except Exception:
                    pass  # hash check is best-effort

            if args.xml_type in ("sftp", "all"):
                sftp_path = getattr(args, "sftp_settings_path", None)
                if sftp_path:
                    try:
                        hash_result = index.check_hash(sftp_path, "sftp")
                        if not hash_result["is_fresh"]:
                            response.add_warning(
                                "Cache may be stale — SFTP config hash mismatch. "
                                "Run 'frp xml rebuild-db' to refresh."
                            )
                    except Exception:
                        pass  # hash check is best-effort

            response.data = {
                "jobs": all_jobs_dicts,
                "total_count": len(all_jobs_dicts),
                "xml_type": args.xml_type,
                "cache_status": "fresh",
                "data_source": "sqlite",
            }

            # Grouped summaries for large result sets
            if len(all_jobs_dicts) > 10:
                by_scrubber: Dict[str, int] = {}
                by_source: Dict[str, int] = {}
                for j in all_jobs_dicts:
                    t = j.get("scrubber", "(none)")
                    by_scrubber[t] = by_scrubber.get(t, 0) + 1
                    source = j.get("mailbox") or j.get("dsn") or "(unknown)"
                    by_source[source] = by_source.get(source, 0) + 1
                response.data["groups_by_scrubber"] = by_scrubber
                response.data["groups_by_source"] = by_source

            index.close()
            return response
        except Exception as exc:
            logger.warning("SQLite query failed, falling back to XML: %s", exc)
            index.close()
            # Fall through to XML parsing

    # ── Fallback: parse XML directly (original logic) ───────────── #
    all_jobs = []

    if args.xml_type in ("email", "all"):
        try:
            parser = SettingsXmlParser(args.settings_path)
            matched = parser.search_jobs(args.query)
            all_jobs.extend(matched)
        except Exception as exc:
            response.add_warning(f"Email XML parse error: {exc}")

    if args.xml_type in ("sftp", "all"):
        sftp_path = getattr(args, "sftp_settings_path", None)
        if sftp_path:
            try:
                parser = SettingsXmlParser(sftp_path)
                matched = parser.search_jobs(args.query)
                all_jobs.extend(matched)
            except Exception as exc:
                response.add_warning(f"SFTP XML parse error: {exc}")
        elif args.xml_type == "sftp":
            response.add_error("--sftp-settings-path is required when xml-type is 'sftp'")
            return response

    response.data = {
        "jobs": [j.to_summary_dict() for j in all_jobs],
        "total_count": len(all_jobs),
        "xml_type": args.xml_type,
        "data_source": "xml",
    }

    # Grouped summaries for large result sets
    if len(all_jobs) > 10:
        # Group by scrubber
        by_scrubber: Dict[str, int] = {}
        for j in all_jobs:
            s = j.to_summary_dict()
            t = s.get("scrubber", "(none)")
            by_scrubber[t] = by_scrubber.get(t, 0) + 1
        response.data["groups_by_scrubber"] = by_scrubber

        # Group by mailbox (email) or DSN (sftp)
        by_source: Dict[str, int] = {}
        for j in all_jobs:
            if hasattr(j, "mailbox"):
                key = j.mailbox
            elif hasattr(j, "dsn"):
                key = j.dsn
            else:
                key = "(unknown)"
            by_source[key] = by_source.get(key, 0) + 1
        response.data["groups_by_source"] = by_source

    return response


def cmd_job_detail(args: argparse.Namespace) -> CliResponse:
    """Return full detail for a single job with tblExternalDIDRef cross-reference."""
    response = CliResponse(success=True, command="job_detail")

    job_name = args.job_name
    target_job = None
    result: Optional[Dict] = None

    # ── Try SQLite cache first ──────────────────────────────────── #
    index = _xml_index_from_args(args)
    if index:
        try:
            cached = index.get_job(job_name)
            if cached:
                result = cached
            index.close()
        except Exception as exc:
            logger.warning("SQLite job_detail failed, falling back to XML: %s", exc)
            index.close()

    # ── Fallback: parse XML directly ────────────────────────────── #
    if result is None:
        # Search email settings
        if args.xml_type in ("email", "all"):
            try:
                parser = SettingsXmlParser(args.settings_path)
                for j in parser.get_all_jobs():
                    if j.name.lower() == job_name.lower():
                        target_job = j
                        break
            except Exception as exc:
                response.add_warning(f"Email XML parse error: {exc}")

        # Search SFTP settings
        if target_job is None and args.xml_type in ("sftp", "all"):
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path:
                try:
                    parser = SettingsXmlParser(sftp_path)
                    for j in parser.get_all_jobs():
                        if j.name.lower() == job_name.lower():
                            target_job = j
                            break
                except Exception as exc:
                    response.add_warning(f"SFTP XML parse error: {exc}")

        if target_job is None:
            response.success = False
            response.add_error(f"Job '{job_name}' not found.")
            return response

        # Build a curated result dict (humanised, no raw JSON dump)
        summary = target_job.to_summary_dict()
        result = {
            "job_name": target_job.name,
            "mailbox": getattr(target_job, "mailbox", None),
            "folder": getattr(target_job, "folder", None),
            "sme": getattr(target_job, "sme", None),
            "last_email": getattr(target_job, "last_email", None),
            "sender": summary.get("sender"),
            "save_path": target_job.save_location,
            "servicer_id": target_job.servicer_id,
            "scrubber": summary.get("scrubber"),
            "match_mode": summary.get("match_mode"),
            "match_mode_description": summary.get("match_mode_description"),
            "queue_one_file": target_job.queue_one_file,
            "xml_type": target_job.xml_type,
        }
        # SFTP-specific fields
        if hasattr(target_job, "path"):
            result["sftp_path"] = target_job.path
            result["dsn"] = getattr(target_job, "dsn", None)
            result.pop("mailbox", None)
            result.pop("folder", None)
        if hasattr(target_job, "zip_content_filter") and target_job.zip_content_filter:
            result["zip_filter"] = target_job.zip_content_filter

        # Strip null / empty values so the LLM doesn't show "Day Adjust: null"
        result = {k: v for k, v in result.items() if v is not None and v != ""}

    # Cross-reference tblExternalDIDRef if the job has a ServicerID
    sid = result.get("servicer_id") if result else None
    if sid:
        db_mode = getattr(args, "db_mode", None)
        if db_mode:
            try:
                repo = _repo_from_args(args)
                deals = repo.get_deals_for_servicer(sid)
                repo.close()
                result["linked_deals"] = deals
                result["linked_deal_count"] = len(deals)
            except Exception as exc:
                response.add_warning(f"DB lookup failed: {exc}")
                result["linked_deals"] = []
                result["linked_deal_count"] = 0
        else:
            result["linked_deals"] = []
            result["linked_deal_count"] = 0
    else:
        result["linked_deals"] = []
        result["linked_deal_count"] = 0
        result["note"] = "No ServicerID — this is a shelf-level/process-level job."

    # ── Recent processing from tblTemplateStaging (Phase 5) ──────── #
    template_name = result.get("scrubber") or result.get("job_name", "")
    try:
        ts_repo = _ts_repo_from_args(args)
        ts_data = ts_repo.get_recent_by_query(template_name, days=30, limit=5)
        result["recent_processing"] = {
            "runs": ts_data.get("runs", []),
            "success_rate": ts_data.get("success_rate", 0),
            "total_runs": ts_data.get("total_runs", 0),
            "last_success": ts_data.get("last_success"),
            "last_failure": ts_data.get("last_failure"),
        }
        ts_repo.close()
    except Exception as exc:
        response.add_warning(f"Template staging unavailable — skipping: {exc}")
        result["recent_processing"] = {}

    response.data = result
    return response


def cmd_deal_lookup(args: argparse.Namespace) -> CliResponse:
    """Look up which jobs serve a given deal by cross-referencing tblExternalDIDRef."""
    response = CliResponse(success=True, command="deal_lookup")

    query = args.query
    db_mode = getattr(args, "db_mode", None)
    lookup_type = getattr(args, "lookup_type", "auto")
    try:
        filters = _parse_deal_lookup_filters(getattr(args, "filters_json", None))
    except ValueError as exc:
        response.success = False
        response.add_error(str(exc))
        return response

    if not db_mode:
        response.success = False
        response.add_error("Database mode (--db-mode) is required for deal lookup.")
        return response

    # ── "all" / "*" → return all records + summary ──────────── #
    is_all = not filters and query.strip().lower() in ("*", "all", "all records")

    try:
        repo = _repo_from_args(args)
        if is_all:
            deals = repo.get_all_deals()
            summary = repo.get_table_summary()
        else:
            if filters:
                deals = repo.search_deals_by_filters(filters)
            elif lookup_type == "did":
                deals = repo.search_by_did(f"%{query}%")
            elif lookup_type == "keyword":
                deals = repo.search_by_import_did(f"%{query}%")
            elif lookup_type in ("company", "servicer"):
                company_id = repo._extract_numeric_id(query)
                deals = repo.get_deals_by_company(company_id) if company_id is not None else []
            else:
                deals = repo.search_deals(query)
            summary = None
        repo.close()
    except Exception as exc:
        response.success = False
        response.add_error(f"DB error: {exc}")
        return response

    if is_all:
        response.data = {
            "query": query,
            "deals": deals[:200],
            "deal_count": len(deals),
            "summary": summary,
            "filters": filters,
            "data_source": {"deals": "tblExternalDIDRef"},
            "note": f"Showing first {min(len(deals), 200)} of {summary['total_rows']} total rows" if summary else None,
        }
        return response

    if not deals:
        response.data = {"deals": [], "matching_jobs": [], "query": query,
                         "filters": filters,
                         "data_source": {"deals": "tblExternalDIDRef", "jobs": "n/a"}}
        return response

    # Get unique CompanyIDs from matched deals
    company_ids = set()
    for d in deals:
        cid = d.get("CompanyID") or d.get("company_id")
        if cid:
            company_ids.add(int(cid))

    # Now find jobs that match those CompanyIDs — SQLite first, XML fallback
    matching_jobs = []
    jobs_source = "xml"

    index = _xml_index_from_args(args)
    if index:
        try:
            matching_jobs = index.find_jobs_by_servicer_ids(company_ids, args.xml_type)
            jobs_source = "sqlite"
            index.close()
        except Exception as exc:
            logger.warning("SQLite job lookup failed, falling back to XML: %s", exc)
            index.close()
            matching_jobs = []  # reset — fall through to XML

    if not matching_jobs and jobs_source != "sqlite":
        if args.xml_type in ("email", "all"):
            try:
                parser = SettingsXmlParser(args.settings_path)
                for j in parser.get_all_jobs():
                    if j.servicer_id and j.servicer_id in company_ids:
                        matching_jobs.append(j.to_summary_dict())
            except Exception as exc:
                response.add_warning(f"Email XML parse error: {exc}")

        if args.xml_type in ("sftp", "all"):
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path:
                try:
                    parser = SettingsXmlParser(sftp_path)
                    for j in parser.get_all_jobs():
                        if j.servicer_id and j.servicer_id in company_ids:
                            matching_jobs.append(j.to_summary_dict())
                except Exception as exc:
                    response.add_warning(f"SFTP XML parse error: {exc}")

    response.data = {
        "query": query,
        "lookup_type": lookup_type,
        "filters": filters,
        "deals": deals[:50],  # cap at 50 for LLM context
        "deal_count": len(deals),
        "matching_jobs": matching_jobs,
        "matching_job_count": len(matching_jobs),
        "data_source": {"deals": "tblExternalDIDRef", "jobs": jobs_source},
    }
    return response


def cmd_validate_xml(args: argparse.Namespace) -> CliResponse:
    """Parse and validate a Settings.xml file."""
    response = CliResponse(success=True, command="validate_xml")

    parser = SettingsXmlParser(args.settings_path)

    db_servicer_ids = None
    db_mode = getattr(args, "db_mode", None)
    if db_mode:
        try:
            repo = _repo_from_args(args)
            db_servicer_ids = repo.get_all_servicer_ids()
            repo.close()
        except Exception as exc:
            response.add_warning(f"Could not connect to DB for cross-validation: {exc}")

    validation_result = parser.validate(db_servicer_ids=db_servicer_ids)
    response.data = validation_result.to_dict()
    return response


def cmd_sync_logs(args: argparse.Namespace) -> CliResponse:
    """Incrementally sync log files into the SQLite index.

    Supports syncing both email and SFTP log folders in a single
    invocation.  When both ``--log-folder`` (email) and
    ``--sftp-log-folder`` are supplied the indexer runs twice and
    the results are merged.
    """
    response = CliResponse(success=True, command="sync_logs")

    email_folder = getattr(args, "log_folder", None)
    sftp_folder = getattr(args, "sftp_log_folder", None)

    if not email_folder and not sftp_folder:
        response.success = False
        response.add_error("At least one of --log-folder or --sftp-log-folder is required.")
        return response

    # Accumulate totals across both passes
    totals = {
        "files_processed": 0,
        "events_indexed": 0,
        "files_skipped": 0,
        "files_errored": 0,
        "events_purged": 0,
        "errors": [],
    }

    def _merge(result: dict) -> None:
        for key in ("files_processed", "events_indexed", "files_skipped",
                    "files_errored", "events_purged"):
            totals[key] += result.get(key, 0)
        totals["errors"].extend(result.get("errors", []))

    with LogIndexer(args.db_path) as indexer:
        if email_folder:
            _merge(indexer.sync(
                log_folder=email_folder,
                log_type="email",
                retention_months=args.retention_months,
            ))
        if sftp_folder:
            _merge(indexer.sync(
                log_folder=sftp_folder,
                log_type="sftp",
                retention_months=args.retention_months,
            ))

    response.data = totals
    return response


def cmd_servicer_dossier(args: argparse.Namespace) -> CliResponse:
    """Build a comprehensive dossier for a servicer or job."""
    response = CliResponse(success=True, command="servicer_dossier")

    servicer_id: int | None = getattr(args, "servicer_id", None)
    job_name: str | None = getattr(args, "job_name", None)
    query: str | None = getattr(args, "query", None)
    dossier: Dict = {}

    if query and servicer_id is None and job_name is None:
        numeric = DealRepository._extract_numeric_id(query)
        if numeric is not None:
            servicer_id = numeric
        else:
            job_name = query.strip()

    # ── Resolve servicer_id from job_name if needed ──────────────── #
    job_config = None
    if job_name and servicer_id is None:
        try:
            parser = SettingsXmlParser(args.settings_path)
            for job in parser.get_all_jobs():
                if job.name.lower() == job_name.lower():
                    job_config = job.to_dict()
                    servicer_id = getattr(job, "servicer_id", None)
                    break

            # Also search SFTP settings if provided
            sftp_path = getattr(args, "sftp_settings_path", None)
            if job_config is None and sftp_path:
                sftp_parser = SettingsXmlParser(sftp_path)
                for job in sftp_parser.get_all_jobs():
                    if job.name.lower() == job_name.lower():
                        job_config = job.to_dict()
                        servicer_id = getattr(job, "servicer_id", None)
                        break

            if job_config is None:
                response.add_warning(f"Job '{job_name}' not found in XML settings")
        except Exception as exc:
            response.add_warning(f"Error searching XML for job '{job_name}': {exc}")

    if servicer_id is None and job_config is None:
        response.add_error("Either --servicer-id or a valid --job-name is required")
        return response

    # ── Job configuration from XML ───────────────────────────────── #
    if job_config is None and servicer_id is not None:
        try:
            parser = SettingsXmlParser(args.settings_path)
            matching_jobs = [
                j for j in parser.get_all_jobs()
                if getattr(j, "servicer_id", None) == servicer_id
            ]
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path:
                try:
                    sftp_parser = SettingsXmlParser(sftp_path)
                    matching_jobs.extend(
                        j for j in sftp_parser.get_all_jobs()
                        if getattr(j, "servicer_id", None) == servicer_id
                    )
                except Exception as exc:
                    response.add_warning(f"SFTP XML parse error: {exc}")
            dossier["jobs"] = [j.to_dict() for j in matching_jobs]
        except Exception as exc:
            response.add_warning(f"Error reading XML settings: {exc}")
            dossier["jobs"] = []
    else:
        dossier["jobs"] = [job_config] if job_config else []

    dossier["servicer_id"] = servicer_id

    # ── Deals from database (graceful degradation) ───────────────── #
    try:
        repo = _repo_from_args(args)
        if servicer_id is not None:
            dossier["deals"] = repo.get_deals_by_company(servicer_id)
            dossier["company_summary"] = repo.get_company_summary(servicer_id)
        else:
            dossier["deals"] = []
            dossier["company_summary"] = {}
        repo.close()
    except Exception as exc:
        response.add_warning(f"Database unavailable — skipping deals section: {exc}")
        dossier["deals"] = []
        dossier["company_summary"] = {}

    # ── Log summary from SQLite (graceful degradation) ───────────── #
    log_db_path = getattr(args, "log_db_path", None)
    if log_db_path:
        try:
            with LogIndexer(log_db_path) as indexer:
                # Summarise logs for every job in the dossier
                log_summaries = []
                for jdata in dossier.get("jobs", []):
                    jname = jdata.get("name")
                    if jname:
                        log_summaries.append(indexer.get_job_summary(jname))
                dossier["log_summaries"] = log_summaries
                dossier["log_index_status"] = indexer.get_sync_status()
        except Exception as exc:
            response.add_warning(f"Log database unavailable — skipping log section: {exc}")
            dossier["log_summaries"] = []
            dossier["log_index_status"] = {}
    else:
        dossier["log_summaries"] = []
        dossier["log_index_status"] = {}

    # ── Template staging data (Phase 5 enrichment, graceful) ─────── #
    if servicer_id is not None:
        try:
            ts_repo = _ts_repo_from_args(args)
            svc_data = ts_repo.get_processing_for_servicer(servicer_id, limit=20)
            dossier["template_staging"] = {
                "summary": svc_data.get("summary", {}),
                "recent_runs": svc_data.get("runs", [])[:10],
            }
            ts_repo.close()
        except Exception as exc:
            response.add_warning(f"Template staging unavailable — skipping: {exc}")
            dossier["template_staging"] = {}
    else:
        dossier["template_staging"] = {}

    response.data = dossier
    return response


def cmd_list_backups(args: argparse.Namespace) -> CliResponse:
    """List available backup files for a Settings.xml file."""
    response = CliResponse(success=True, command="list_backups")

    manager = BackupManager(args.settings_path)
    backups = manager.list_backups()

    response.data = {
        "backups": backups,
        "backup_folder": manager.backup_dir,
    }
    return response


def cmd_save_xml(args: argparse.Namespace) -> CliResponse:
    """Re-save the current Settings.xml (creating a backup first)."""
    response = CliResponse(success=True, command="save_xml")

    parser = SettingsXmlParser(args.settings_path)
    tree = parser.get_element_tree()

    writer = XmlWriter(args.settings_path)
    result = writer.save(tree)

    response.data = {
        "success": result.get("success", False),
        "backup_created": bool(result.get("backup_path")),
        "message": result.get("message", ""),
    }
    if not result.get("success"):
        response.add_error(result.get("message", "Save failed"))

    return response


def cmd_status(args: argparse.Namespace) -> CliResponse:
    """Return basic runtime / version status information."""
    response = CliResponse(success=True, command="status")

    response.data = {
        "version": __version__,
        "python_version": sys.version,
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "settings_files": {
            "email": os.environ.get("FRP_EMAIL_SETTINGS_PATH", "(not set)"),
            "sftp": os.environ.get("FRP_SFTP_SETTINGS_PATH", "(not set)"),
        },
    }
    return response


# ── Phase 2 command handlers ─────────────────────────────────────── #

def cmd_create_job(args: argparse.Namespace) -> CliResponse:
    """Create a new job from a template."""
    response = CliResponse(success=True, command="create_job")
    from backend.xml.crud import JobCrudEngine
    overrides = {}
    if getattr(args, 'servicer_id', None):
        overrides['servicer_id'] = args.servicer_id
    if getattr(args, 'mailbox', None):
        overrides['mailbox'] = args.mailbox
    if getattr(args, 'import_did', None):
        overrides['import_did'] = args.import_did
    try:
        engine = JobCrudEngine(args.settings_path, args.xml_type)
        result = engine.create_job(args.template_job, args.name, overrides or None)
        response.data = result.to_dict()
        _rebuild_sqlite(args)  # rebuild cache after write
    except (ValueError, FileNotFoundError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_next_servicer_id(args: argparse.Namespace) -> CliResponse:
    """Find the next unused ServicerID in a series by querying the SQLite cache."""
    response = CliResponse(success=True, command="next_servicer_id")
    from backend.db.xml_index import XmlJobIndex
    try:
        base = int(args.base_id)
        with XmlJobIndex(args.cache_db_path) as index:
            next_id = index.next_servicer_id(base)
        response.data = {
            "base_id": base,
            "next_available_servicer_id": next_id,
        }
    except (ValueError, TypeError) as exc:
        response.success = False
        response.add_error(f"Invalid base_id: {exc}")
    return response


def cmd_edit_job(args: argparse.Namespace) -> CliResponse:
    """Edit a field on an existing job."""
    response = CliResponse(success=True, command="edit_job")
    from backend.xml.crud import JobCrudEngine
    try:
        engine = JobCrudEngine(args.settings_path, args.xml_type)
        result = engine.edit_job(args.job_name, args.field, args.value)
        response.data = result.to_dict()
        _rebuild_sqlite(args)  # rebuild cache after write
    except (ValueError, FileNotFoundError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_clone_prepare(args: argparse.Namespace) -> CliResponse:
    """Resolve a source job by ServicerID and enumerate clone fields."""
    response = CliResponse(success=True, command="clone_prepare")
    from backend.xml.clone import JobCloneEngine

    try:
        engine = JobCloneEngine(args.settings_path, getattr(args, "sftp_settings_path", None))
        response.data = engine.prepare_clone(int(args.source_servicer_id))
    except (ValueError, FileNotFoundError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_clone_preview(args: argparse.Namespace) -> CliResponse:
    """Preview a deterministic clone before writing Settings.xml."""
    response = CliResponse(success=True, command="clone_preview")
    from backend.xml.clone import JobCloneEngine

    try:
        overrides = json.loads(args.overrides_json) if getattr(args, "overrides_json", None) else {}
        if overrides and not isinstance(overrides, dict):
            raise ValueError("--overrides-json must be a JSON object mapping field paths to values.")
        engine = JobCloneEngine(args.settings_path, getattr(args, "sftp_settings_path", None))
        response.data = engine.preview_clone(
            int(args.source_servicer_id),
            args.clone_job_name,
            int(args.assigned_servicer_id),
            overrides,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_clone_apply(args: argparse.Namespace) -> CliResponse:
    """Apply a deterministic clone to Settings.xml."""
    response = CliResponse(success=True, command="clone_apply")
    from backend.xml.clone import JobCloneEngine

    try:
        overrides = json.loads(args.overrides_json) if getattr(args, "overrides_json", None) else {}
        if overrides and not isinstance(overrides, dict):
            raise ValueError("--overrides-json must be a JSON object mapping field paths to values.")
        engine = JobCloneEngine(args.settings_path, getattr(args, "sftp_settings_path", None))
        response.data = engine.apply_clone(
            int(args.source_servicer_id),
            args.clone_job_name,
            int(args.assigned_servicer_id),
            overrides,
        )
        args.xml_type = response.data.get("xml_type", getattr(args, "xml_type", "email"))
        _rebuild_sqlite(args)
    except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_template_inventory(args: argparse.Namespace) -> CliResponse:
    """Discover template patterns in Settings.xml."""
    response = CliResponse(success=True, command="template_inventory")
    from backend.xml.templates import TemplateInventory
    inventory = TemplateInventory(args.settings_path, args.xml_type)
    templates = inventory.discover_templates(getattr(args, 'filter', None))
    response.data = {
        "templates": [t.to_dict() for t in templates],
        "total_templates": len(templates),
        "total_jobs": sum(t.job_count for t in templates),
    }
    return response


def cmd_coverage_gaps(args: argparse.Namespace) -> CliResponse:
    """Analyse coverage gaps between XML jobs and DB records."""
    response = CliResponse(success=True, command="coverage_gaps")
    from backend.intel.coverage import CoverageAnalyzer
    repo = _repo_from_args(args)
    try:
        analyzer = CoverageAnalyzer(args.settings_path, repo, args.xml_type)
        sid = int(args.servicer_id) if args.servicer_id and args.servicer_id != 'all' else None
        reports = analyzer.analyze(sid)
        response.data = {
            "reports": [r.to_dict() for r in reports],
            "total_servicers_analyzed": len(reports),
        }
    finally:
        repo.close()
    return response


def cmd_orphan_detection(args: argparse.Namespace) -> CliResponse:
    """Detect orphaned jobs with no valid DB match."""
    response = CliResponse(success=True, command="orphan_detection")
    from backend.intel.orphans import OrphanDetector
    repo = _repo_from_args(args)
    try:
        detector = OrphanDetector(args.settings_path, repo, args.xml_type)
        orphans = detector.detect()
        response.data = {
            "orphans": [o.to_dict() for o in orphans],
            "total_orphans": len(orphans),
        }
    finally:
        repo.close()
    return response


def cmd_collision_detection(args: argparse.Namespace) -> CliResponse:
    """Detect ImportDID collisions (same keyword → multiple companies)."""
    response = CliResponse(success=True, command="collision_detection")
    from backend.intel.collisions import CollisionDetector
    repo = _repo_from_args(args)
    try:
        detector = CollisionDetector(args.settings_path, repo, args.xml_type)
        collisions = detector.detect()
        response.data = {
            "collisions": [c.to_dict() for c in collisions],
            "total_collisions": len(collisions),
        }
    finally:
        repo.close()
    return response


def cmd_xml_diff(args: argparse.Namespace) -> CliResponse:
    """Diff Settings.xml against a backup file."""
    response = CliResponse(success=True, command="xml_diff")
    from backend.xml.diff import XmlDiffEngine
    backup_file = args.backup_file
    if not backup_file:
        manager = BackupManager(args.settings_path)
        latest = manager.get_latest_backup()
        if not latest:
            response.add_error("No backups found. Run save_xml first.")
            return response
        backup_file = latest.get("full_path", "")
    engine = XmlDiffEngine(args.xml_type)
    result = engine.diff(args.settings_path, backup_file)
    response.data = result.to_dict()
    return response


def cmd_rollback_xml(args: argparse.Namespace) -> CliResponse:
    """Rollback Settings.xml to a backup file."""
    response = CliResponse(success=True, command="rollback_xml")
    from backend.xml.rollback import RollbackHandler
    try:
        handler = RollbackHandler(args.settings_path, args.xml_type)
        result = handler.execute(args.backup_file)
        response.data = result
    except (ValueError, FileNotFoundError, OSError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


# ── Phase 3 command handlers ─────────────────────────────────────── #

def cmd_log_deal_activity(args: argparse.Namespace) -> CliResponse:
    """Query deal-related activity from the log index."""
    response = CliResponse(success=True, command="log_deal_activity")
    try:
        from backend.logs.analytics import LogAnalytics

        analytics = LogAnalytics(args.db_path)
        staleness = analytics.check_staleness()

        import_did = None
        if getattr(args, "db_mode", None):
            try:
                repo = _repo_from_args(args)
                import_did = repo.resolve_did_by_name(args.did)
                repo.close()
            except Exception:
                pass

        events = analytics.deal_activity(
            args.did, getattr(args, "days", 30), import_did
        )
        response.data = {
            "did_identifier": args.did,
            "resolved_import_did": import_did or args.did,
            "date_range": f"Last {args.days} days",
            "total_events": len(events),
            "events": [e.to_dict() for e in events],
        }
        if staleness:
            response.data["warning"] = staleness["warning"]
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_did_failures(args: argparse.Namespace) -> CliResponse:
    """Aggregate DID-mapping failures from the log index."""
    response = CliResponse(success=True, command="log_did_failures")
    try:
        from backend.logs.analytics import LogAnalytics

        analytics = LogAnalytics(args.db_path)
        staleness = analytics.check_staleness()

        failures = analytics.did_failures(
            getattr(args, "days", 30),
            getattr(args, "job_filter", None),
        )
        response.data = {
            "date_range": f"Last {args.days} days",
            "total_unique_dids": len(failures),
            "total_failures": sum(f.failure_count for f in failures),
            "failures": [f.to_dict() for f in failures],
        }
        if staleness:
            response.data["warning"] = staleness["warning"]
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_job_health(args: argparse.Namespace) -> CliResponse:
    """Compute health metrics for a specific job."""
    response = CliResponse(success=True, command="log_job_health")
    try:
        from backend.logs.analytics import LogAnalytics

        analytics = LogAnalytics(args.db_path)
        staleness = analytics.check_staleness()

        health = analytics.job_health(args.job_name, getattr(args, "days", 30))
        response.data = health.to_dict()
        if staleness:
            response.data["warning"] = staleness["warning"]
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_daily_summary(args: argparse.Namespace) -> CliResponse:
    """Compute a one-day operational summary from the log index."""
    response = CliResponse(success=True, command="log_daily_summary")
    try:
        from backend.logs.analytics import LogAnalytics

        analytics = LogAnalytics(args.db_path)
        staleness = analytics.check_staleness()

        summary = analytics.daily_summary(getattr(args, "date", None))
        response.data = summary.to_dict()
        if staleness:
            response.data["warning"] = staleness["warning"]
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_triage_verify(args: argparse.Namespace) -> CliResponse:
    """Parse a .msg file and verify it matches an existing job."""
    response = CliResponse(success=True, command="triage_verify")
    try:
        from backend.triage.analyzer import TriageAnalyzer

        deal_repo = None
        log_indexer = None
        ts_repo = None

        if getattr(args, "db_mode", None):
            try:
                deal_repo = _repo_from_args(args)
            except Exception:
                pass

        # Optional: log indexer for execution-history cross-reference
        log_dir = getattr(args, "log_dir", None)
        if log_dir:
            try:
                from backend.logs.indexer import LogIndexer

                log_indexer = LogIndexer(log_dir)
            except Exception:
                pass

        # Optional: template staging repo for scrubber-run cross-reference
        if getattr(args, "db_mode", None):
            try:
                ts_repo = _ts_repo_from_args(args)
            except Exception:
                pass

        analyzer = TriageAnalyzer(
            args.settings_path,
            getattr(args, "xml_type", "email"),
            deal_repo=deal_repo,
            log_indexer=log_indexer,
            ts_repo=ts_repo,
        )
        result = analyzer.verify(args.msg_path)
        response.data = result.to_dict()

        if deal_repo:
            deal_repo.close()
        if ts_repo:
            ts_repo.close()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_triage_match(args: argparse.Namespace) -> CliResponse:
    """Match an email (by .msg or sender/subject) to existing jobs."""
    response = CliResponse(success=True, command="triage_match")
    try:
        from backend.triage.analyzer import TriageAnalyzer

        analyzer = TriageAnalyzer(
            args.settings_path,
            getattr(args, "xml_type", "email"),
        )
        result = analyzer.match_only(
            msg_path=getattr(args, "msg_path", None),
            sender=getattr(args, "sender", None),
            subject=getattr(args, "subject", None),
        )
        response.data = result.to_dict()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_triage_new(args: argparse.Namespace) -> CliResponse:
    """Analyze a .msg file for new-job creation suggestions."""
    response = CliResponse(success=True, command="triage_new")
    try:
        from backend.triage.analyzer import TriageAnalyzer

        deal_repo = None
        if getattr(args, "db_mode", None):
            try:
                deal_repo = _repo_from_args(args)
            except Exception:
                pass

        analyzer = TriageAnalyzer(
            args.settings_path,
            getattr(args, "xml_type", "email"),
            deal_repo,
        )
        result = analyzer.analyze_new(args.msg_path)
        response.data = result.to_dict()

        if deal_repo:
            deal_repo.close()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


# ===================================================================== #
#  Argument parser construction
# ===================================================================== #

# ── Phase 4 command handlers ─────────────────────────────────────── #

def cmd_log_trends(args: argparse.Namespace) -> CliResponse:
    """L-06: Timeline trend analysis."""
    response = CliResponse(success=True, command="log_trends")
    try:
        from backend.logs.analytics import LogAnalytics
        from backend.analysis.trends import TrendAnalyzer

        analytics = LogAnalytics(args.db_path)
        analyzer = TrendAnalyzer(analytics)

        result = analyzer.analyze(
            days=getattr(args, "days", 14),
            job_filter=getattr(args, "job", None),
        )
        response.data = result.to_dict()
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_performance(args: argparse.Namespace) -> CliResponse:
    """L-07: Job performance benchmarking."""
    response = CliResponse(success=True, command="log_performance")
    try:
        from backend.logs.analytics import LogAnalytics
        from backend.analysis.performance import PerformanceBenchmarker

        analytics = LogAnalytics(args.db_path)

        parser = None
        if getattr(args, "settings_path", None):
            try:
                xml_parser = SettingsXmlParser(args.settings_path)
                parser = xml_parser
            except Exception:
                pass

        benchmarker = PerformanceBenchmarker(analytics, parser)
        result = benchmarker.benchmark(
            sort_by=getattr(args, "sort", "success_rate"),
            ascending=getattr(args, "ascending", True),
            top_n=getattr(args, "top", None),
            days=getattr(args, "days", 30),
        )
        response.data = result.to_dict()
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_search(args: argparse.Namespace) -> CliResponse:
    """Search log events with deterministic-ready structured filters."""
    response = CliResponse(success=True, command="log_search")
    try:
        query = getattr(args, "query", "") or ""
        mode = str(getattr(args, "mode", None) or getattr(args, "event_type", None) or "summary").strip().lower()
        if mode == "detail":
            mode = "details"
        limit = int(getattr(args, "limit", 50) or 50)
        days = getattr(args, "days", None)
        start_date = _normalise_log_start(getattr(args, "start_date", None), days)
        end_date = _normalise_log_end(getattr(args, "end_date", None))
        filters = _normalise_log_filters(getattr(args, "filters", None))
        filter_map = {entry["field"]: entry["value"] for entry in filters}
        job_filter = getattr(args, "job_name", None) or filter_map.get("job_name")
        event_filter = filter_map.get("event_type")

        with LogIndexer(args.db_path) as indexer:
            if mode == "errors" and query and not filters and not start_date and not end_date and not getattr(args, "job_name", None):
                errors = indexer.get_job_errors(query, limit=limit)
                summary = indexer.get_job_summary(query) if errors else {}
                response.data = {
                    "query": query,
                    "mode": "error_details",
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "errors": errors,
                    "error_count": len(errors),
                    "summary": summary,
                }
                return response

            if mode == "activity" and query and not filters and not start_date and not end_date and not getattr(args, "job_name", None):
                events = indexer.get_job_activity(query, limit=limit)
                response.data = {
                    "query": query,
                    "mode": "activity",
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "events": events,
                    "event_count": len(events),
                    "summary": _build_log_event_summary(events),
                }
                return response

            simple_summary = mode == "summary" and query and not filters and not start_date and not end_date and not getattr(args, "job_name", None)
            if simple_summary:
                jobs = indexer.search_jobs(query, limit=min(limit, 20))
                for job in jobs:
                    if job.get("total_errors", 0) > 0:
                        job["recent_errors"] = indexer.get_job_errors(
                            job["job_name"], limit=5,
                        )
                response.data = {
                    "query": query,
                    "mode": "summary",
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "jobs": jobs,
                    "job_count": len(jobs),
                }
                return response

            events = indexer.query_events(
                job_name=job_filter,
                job_name_like=None,
                event_type=event_filter,
                start_date=start_date,
                end_date=end_date,
                limit=max(limit, 50) if mode == "summary" else limit,
                mailbox=filter_map.get("mailbox"),
                sender=filter_map.get("sender"),
                parser=filter_map.get("parser"),
                filename=filter_map.get("filename"),
                subject=filter_map.get("subject"),
                template=filter_map.get("template"),
                log_type=filter_map.get("log_type"),
                text=query if query else None,
            )
            filtered_events = _filter_log_events_by_mode(events, mode)

            if mode == "summary":
                jobs = _summarise_log_events(filtered_events, limit=min(limit, 20))
                response.data = {
                    "query": query,
                    "mode": "summary",
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "jobs": jobs,
                    "job_count": len(jobs),
                    "summary": _build_log_event_summary(filtered_events),
                }
            elif mode in ("email", "emails"):
                email_events = _group_log_events_by_email(events, limit=limit)
                response.data = {
                    "query": query,
                    "mode": "emails",
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "email_events": email_events,
                    "email_count": len(email_events),
                    "event_count": len(events),
                    "summary": _build_log_event_summary(events),
                }
            else:
                response.data = {
                    "query": query,
                    "mode": mode,
                    "filters": filters,
                    "period": {"days": days, "start_date": start_date, "end_date": end_date},
                    "events": filtered_events,
                    "event_count": len(filtered_events),
                    "jobs": _summarise_log_events(filtered_events, limit=10),
                    "summary": _build_log_event_summary(filtered_events),
                }
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_log_linkage(args: argparse.Namespace) -> CliResponse:
    """Cross-link log evidence to jobs, deals, and recent staging activity."""
    response = CliResponse(success=True, command="log_linkage")
    deal_repo = None
    ts_repo = None
    try:
        query = getattr(args, "query", "") or ""
        limit = int(getattr(args, "limit", 25) or 25)
        days = getattr(args, "days", 30)
        start_date = _normalise_log_start(getattr(args, "start_date", None), days)
        end_date = _normalise_log_end(getattr(args, "end_date", None))
        filters = _normalise_log_filters(getattr(args, "filters", None))
        filter_map = {entry["field"]: entry["value"] for entry in filters}

        with LogIndexer(args.db_path) as indexer:
            events = indexer.query_events(
                job_name=filter_map.get("job_name"),
                job_name_like=None,
                event_type=filter_map.get("event_type"),
                start_date=start_date,
                end_date=end_date,
                limit=max(limit * 3, 30),
                mailbox=filter_map.get("mailbox"),
                sender=filter_map.get("sender"),
                parser=filter_map.get("parser"),
                filename=filter_map.get("filename"),
                subject=filter_map.get("subject"),
                template=filter_map.get("template"),
                log_type=filter_map.get("log_type"),
                text=query if query else None,
            )
            job_summaries = _summarise_log_events(events, limit=10)
            if not job_summaries and query:
                job_summaries = indexer.search_jobs(query, limit=10)

        matched_job_names = [row.get("job_name") for row in job_summaries if row.get("job_name")]
        reference_jobs, jobs_source = _collect_staging_reference_jobs(args)
        linked_jobs = _match_log_reference_jobs(reference_jobs, matched_job_names, query)
        if not linked_jobs and query:
            linked_jobs = _match_jobs_by_scrubber(reference_jobs, query)

        linked_deals: List[Dict] = []
        servicer_summaries: List[Dict] = []
        if getattr(args, "db_mode", None):
            deal_repo = _repo_from_args(args)
            numeric_query = DealRepository._extract_numeric_id(query) if query else None
            if numeric_query is not None:
                linked_deals.extend(deal_repo.get_deals_by_company(numeric_query))

            if query:
                linked_deals.extend(deal_repo.search_deals(query))

            servicer_ids = sorted({
                job.get("servicer_id") for job in linked_jobs
                if job.get("servicer_id") not in (None, "")
            })
            for servicer_id in servicer_ids:
                deals = deal_repo.get_deals_by_company(int(servicer_id))
                linked_deals.extend(deals)
                servicer_summaries.append({"servicer_id": servicer_id, "deal_count": len(deals)})
            linked_deals = _dedupe_deal_rows(linked_deals)

        staging_rows: List[Dict] = []
        if getattr(args, "db_mode", None):
            ts_repo = _ts_repo_from_args(args)
            seen_stage_ids = set()

            def _push_staging(rows: List[Dict]) -> None:
                for row in rows:
                    row_id = row.get("TemplateProcessID")
                    if row_id in seen_stage_ids:
                        continue
                    seen_stage_ids.add(row_id)
                    staging_rows.append(_summarise_staging_record(row))

            for job in linked_jobs[:8]:
                scrubber = job.get("scrubber") or job.get("template")
                if scrubber:
                    _push_staging(ts_repo.advanced_search(
                        filters=[{"field": "template", "value": str(scrubber)}],
                        days=days,
                        limit=min(limit, 10),
                    ))

            if query:
                _push_staging(ts_repo.advanced_search(query=query, days=days, limit=min(limit, 10)))

            for deal in linked_deals[:5]:
                did_value = deal.get("DID") or deal.get("did")
                if did_value:
                    _push_staging(ts_repo.advanced_search(
                        filters=[{"field": "did", "value": str(did_value)}],
                        days=days,
                        limit=5,
                    ))

        response.data = {
            "query": query,
            "filters": filters,
            "period": {"days": days, "start_date": start_date, "end_date": end_date},
            "events": events[:limit],
            "event_count": len(events),
            "summary": _build_log_event_summary(events),
            "log_jobs": job_summaries,
            "linked_jobs": linked_jobs,
            "linked_job_count": len(linked_jobs),
            "job_context": _build_staging_jobs_context(linked_jobs),
            "linked_deals": linked_deals,
            "linked_deal_count": len(linked_deals),
            "servicer_summaries": servicer_summaries,
            "recent_staging": staging_rows[:limit],
            "staging_summary": _build_staging_summary(staging_rows),
            "data_source": {
                "logs": "sqlite",
                "jobs": jobs_source,
                "deals": "tblExternalDIDRef" if linked_deals else "unavailable",
                "staging": "tblTemplateStaging" if staging_rows else "unavailable",
            },
        }
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    finally:
        if deal_repo:
            deal_repo.close()
        if ts_repo:
            ts_repo.close()
    return response


def cmd_analyze_consolidation(args: argparse.Namespace) -> CliResponse:
    """A-01: Job consolidation analysis."""
    response = CliResponse(success=True, command="analyze_consolidation")
    try:
        from backend.analysis.consolidation import ConsolidationAnalyzer

        parser = SettingsXmlParser(args.settings_path)

        deal_repo = None
        if getattr(args, "db_mode", None):
            try:
                deal_repo = _repo_from_args(args)
            except Exception as e:
                logger.warning(f"DB connection failed, running without DID counts: {e}")

        analyzer = ConsolidationAnalyzer(parser, deal_repo)
        result = analyzer.analyze(
            xml_type=getattr(args, "type", "all"),
        )
        response.data = result.to_dict()

        if deal_repo:
            deal_repo.close()
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_analyze_impact(args: argparse.Namespace) -> CliResponse:
    """A-02: Change impact simulation."""
    response = CliResponse(success=True, command="analyze_impact")
    try:
        from backend.analysis.impact import ImpactSimulator
        from backend.analysis.models import ChangeSpec

        parser = SettingsXmlParser(args.settings_path)

        deal_repo = None
        analytics = None
        if getattr(args, "db_mode", None):
            try:
                deal_repo = _repo_from_args(args)
            except Exception as e:
                logger.warning(f"DB connection failed: {e}")

        if getattr(args, "db_path", None):
            try:
                from backend.logs.analytics import LogAnalytics
                analytics = LogAnalytics(args.db_path)
            except Exception as e:
                logger.warning(f"Log analytics unavailable: {e}")

        change = ChangeSpec(
            change_type=args.change_type,
            target_job=getattr(args, "target_job", None),
            target_did=getattr(args, "target_did", None),
            target_company_id=getattr(args, "target_company_id", None),
            new_value=getattr(args, "new_value", None),
            raw_description=getattr(args, "raw_description", ""),
        )

        simulator = ImpactSimulator(parser, deal_repo, analytics)
        result = simulator.simulate(change)
        response.data = result.to_dict()

        if deal_repo:
            deal_repo.close()
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_analyze_health(args: argparse.Namespace) -> CliResponse:
    """A-03: Full system health check."""
    response = CliResponse(success=True, command="analyze_health")
    try:
        from backend.analysis.health import HealthChecker

        xml_parser = None
        deal_repo = None
        analytics = None
        coverage = None
        orphans = None
        collisions = None
        benchmarker = None

        if getattr(args, "settings_path", None):
            try:
                xml_parser = SettingsXmlParser(args.settings_path)
            except Exception as e:
                logger.warning(f"Settings parser failed: {e}")

        if getattr(args, "db_mode", None):
            try:
                deal_repo = _repo_from_args(args)
            except Exception as e:
                logger.warning(f"DB connection failed: {e}")

        if getattr(args, "db_path", None):
            try:
                from backend.logs.analytics import LogAnalytics
                analytics = LogAnalytics(args.db_path)
            except Exception as e:
                logger.warning(f"Log analytics failed: {e}")

        if xml_parser and deal_repo:
            try:
                from backend.intel.coverage import CoverageAnalyzer
                from backend.intel.orphans import OrphanDetector
                from backend.intel.collisions import CollisionDetector
                coverage = CoverageAnalyzer(xml_parser.settings_path, deal_repo, "all")
                orphans = OrphanDetector(xml_parser.settings_path, deal_repo, "all")
                collisions = CollisionDetector(xml_parser.settings_path, deal_repo, "all")
            except Exception as e:
                logger.warning(f"Intel modules failed: {e}")

        if analytics:
            try:
                from backend.analysis.performance import PerformanceBenchmarker
                benchmarker = PerformanceBenchmarker(analytics, xml_parser)
            except Exception as e:
                logger.warning(f"Benchmarker failed: {e}")

        checker = HealthChecker(
            parser=xml_parser,
            deal_repo=deal_repo,
            analytics=analytics,
            coverage_analyzer=coverage,
            orphan_detector=orphans,
            collision_detector=collisions,
            benchmarker=benchmarker,
        )
        result = checker.check(xml_type=getattr(args, "type", "all"))
        response.data = result.to_dict()

        # ── Processing health from tblTemplateStaging (Phase 5) ──── #
        try:
            ts_repo = _ts_repo_from_args(args)
            summary = ts_repo.get_summary()
            failure_data = ts_repo.get_failure_summary(days=30)
            manual_data = ts_repo.get_manual_queue_stats(days=30)
            ts_repo.close()

            total = summary.get("total_runs", 0)
            successes = summary.get("successes", 0)
            overall_rate = round((successes / total * 100), 1) if total else 0.0

            # Flag templates with >10% failure rate
            flagged_templates = [
                t for t in failure_data.get("top_templates", [])
                if t.get("failure_count", 0) > 0
            ]

            response.data["processing_health"] = {
                "overall_success_rate": overall_rate,
                "total_runs": total,
                "successes": successes,
                "failures": summary.get("failures", 0),
                "flagged_templates": flagged_templates[:10],
                "manual_queue_percentage": manual_data.get("manual_percentage", 0),
                "unique_templates": summary.get("unique_templates", 0),
                "unique_deals": summary.get("unique_deals", 0),
            }
        except Exception as exc:
            response.add_warning(f"Template staging unavailable — skipping processing health: {exc}")
            response.data["processing_health"] = {}

        if deal_repo:
            deal_repo.close()
    except (FileNotFoundError, ValueError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response


# ===================================================================== #
#  Phase 5 — tblTemplateStaging command handlers
# ===================================================================== #


def cmd_template_status(args: argparse.Namespace) -> CliResponse:
    """UC-01: Check processing status for a deal or template."""
    response = CliResponse(success=True, command="template_status")
    try:
        repo = _ts_repo_from_args(args)
        data = repo.get_recent_by_query(
            query=args.query,
            days=getattr(args, "days", 30),
            limit=getattr(args, "limit", 10),
        )
        repo.close()
        response.data = data
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_processing_history(args: argparse.Namespace) -> CliResponse:
    """UC-02: Full processing history for a deal, servicer, or template."""
    response = CliResponse(success=True, command="processing_history")
    try:
        repo = _ts_repo_from_args(args)
        start_date = getattr(args, "start_date", None)
        end_date = getattr(args, "end_date", None)
        limit = getattr(args, "limit", 50)

        logger.info(
            "processing_history: query=%r, start_date=%r, end_date=%r, limit=%r",
            args.query, start_date, end_date, limit,
        )

        if start_date and end_date:
            try:
                sid = int(args.query)
                logger.info("processing_history: date+servicer branch (sid=%d)", sid)
                runs = repo.get_by_date_range(start_date, end_date)
                runs = [r for r in runs if r.get("ServicerID") == sid][:limit]
            except ValueError:
                logger.info("processing_history: date+query branch (query=%r)", args.query)
                runs = repo.search_by_query_and_date_range(
                    args.query, start_date, end_date, limit,
                )
            logger.info(
                "processing_history: date branch returned %d rows", len(runs),
            )
        else:
            try:
                sid = int(args.query)
                logger.info("processing_history: no-date servicer branch (sid=%d)", sid)
                svc_data = repo.get_processing_for_servicer(
                    sid, limit=limit,
                )
                runs = svc_data.get("runs", [])
            except ValueError:
                logger.info("processing_history: no-date query branch (query=%r)", args.query)
                data = repo.get_recent_by_query(
                    query=args.query,
                    days=365,
                    limit=limit,
                )
                runs = data.get("runs", [])
            logger.info(
                "processing_history: no-date branch returned %d rows", len(runs),
            )

        # Cross-reference tblExternalDIDRef for enrichment
        deal_info = {}
        try:
            deal_repo = _repo_from_args(args)
            sids = {r.get("ServicerID") for r in runs if r.get("ServicerID")}
            for sid in sids:
                if sid:
                    deals = deal_repo.get_deals_by_company(sid)
                    deal_info[sid] = deals
            deal_repo.close()
        except Exception:
            pass

        total = len(runs)
        successes = sum(1 for r in runs if r.get("ResultCode") == 0)
        failures = total - successes
        templates_used = list({r.get("TemplateName") for r in runs if r.get("TemplateName")})

        response.data = {
            "query": args.query,
            "date_range": {"start": start_date, "end": end_date}
                if start_date and end_date else None,
            "runs": runs,
            "summary": {
                "total_files": total,
                "successes": successes,
                "failures": failures,
                "unique_templates": templates_used,
            },
            "deal_info": {str(k): v for k, v in deal_info.items()},
        }
        repo.close()
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_failure_analysis(args: argparse.Namespace) -> CliResponse:
    """UC-03: Failure deep-dive."""
    response = CliResponse(success=True, command="failure_analysis")
    try:
        repo = _ts_repo_from_args(args)
        data = repo.get_failure_summary(
            days=getattr(args, "days", 30),
            template=getattr(args, "template", None),
            did=getattr(args, "did", None),
        )

        # Only include individual failures if --detail is set
        if not getattr(args, "detail", False):
            data.pop("failures", None)

        repo.close()
        response.data = data
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_source_trace(args: argparse.Namespace) -> CliResponse:
    """UC-04: Trace file origin to processing."""
    response = CliResponse(success=True, command="source_trace")
    try:
        repo = _ts_repo_from_args(args)
        traces = repo.trace_by_filepath(
            filepath_pattern=args.filepath,
            limit=getattr(args, "limit", 10),
        )
        repo.close()
        response.data = {
            "filepath_query": args.filepath,
            "traces": traces,
            "match_count": len(traces),
        }
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_manual_queue_report(args: argparse.Namespace) -> CliResponse:
    """UC-05: Manual vs automated processing breakdown."""
    response = CliResponse(success=True, command="manual_queue_report")
    try:
        repo = _ts_repo_from_args(args)
        data = repo.get_manual_queue_stats(days=getattr(args, "days", 30))
        repo.close()
        response.data = data
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_processing_duration(args: argparse.Namespace) -> CliResponse:
    """UC-06: Processing time analysis."""
    response = CliResponse(success=True, command="processing_duration")
    try:
        repo = _ts_repo_from_args(args)
        data = repo.get_duration_stats(
            days=getattr(args, "days", 30),
            template=getattr(args, "template", None),
        )

        # Sort by user-selected key
        sort_key = getattr(args, "sort", "avg_seconds") or "avg_seconds"
        if data.get("templates"):
            data["templates"].sort(
                key=lambda t: t.get(sort_key, 0) or 0,
                reverse=True,
            )

        repo.close()
        response.data = data
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_deal_pipeline(args: argparse.Namespace) -> CliResponse:
    """UC-07: End-to-end pipeline visibility for a deal or servicer."""
    response = CliResponse(success=True, command="deal_pipeline")
    try:
        query = args.query
        days = getattr(args, "days", 30)

        # Resolve ServicerID
        servicer_id = None
        try:
            servicer_id = int(query)
        except ValueError:
            # Try to find servicer via tblExternalDIDRef
            try:
                deal_repo = _repo_from_args(args)
                companies = deal_repo.get_companies_by_import_did(query)
                if companies:
                    servicer_id = companies[0]
                deal_repo.close()
            except Exception:
                pass

        result: Dict = {"query": query, "period_days": days}

        # Config layer: Settings.xml
        settings_path = getattr(args, "settings_path", None)
        if settings_path:
            try:
                parser = SettingsXmlParser(settings_path)
                if servicer_id:
                    matching_jobs = [
                        j.to_dict() for j in parser.get_all_jobs()
                        if getattr(j, "servicer_id", None) == servicer_id
                    ]
                else:
                    matching_jobs = [
                        j.to_dict() for j in parser.get_all_jobs()
                        if query.lower() in (getattr(j, "name", "") or "").lower()
                        or query.lower() in (getattr(j, "template", "") or "").lower()
                    ]
                result["config_layer"] = {
                    "status": "ok" if matching_jobs else "missing",
                    "jobs": matching_jobs,
                    "count": len(matching_jobs),
                }
            except Exception as exc:
                result["config_layer"] = {"status": "error", "error": str(exc), "jobs": [], "count": 0}
        else:
            result["config_layer"] = {"status": "unavailable", "jobs": [], "count": 0}

        # Mapping layer: tblExternalDIDRef
        try:
            deal_repo = _repo_from_args(args)
            if servicer_id:
                deals = deal_repo.get_deals_by_company(servicer_id)
            else:
                deals = deal_repo.search_deals(query)
            result["mapping_layer"] = {
                "status": "ok" if deals else "missing",
                "deals": deals,
                "count": len(deals),
            }
            deal_repo.close()
        except Exception as exc:
            result["mapping_layer"] = {"status": "error", "error": str(exc), "deals": [], "count": 0}

        # Execution layer: tblTemplateStaging
        try:
            ts_repo = _ts_repo_from_args(args)
            if servicer_id:
                pipeline = ts_repo.get_pipeline_status(servicer_id, days)
                result["execution_layer"] = pipeline.get("execution_layer", {})
            else:
                recent = ts_repo.get_recent_by_query(query, days=days, limit=20)
                runs = recent.get("runs", [])
                total = len(runs)
                successes = sum(1 for r in runs if r.get("ResultCode") == 0)
                health = round((successes / total * 100), 1) if total else 0.0
                result["execution_layer"] = {
                    "status": "ok" if health >= 90 else ("warning" if health >= 50 else "critical"),
                    "total_runs": total,
                    "successes": successes,
                    "failures": total - successes,
                    "health_score": health,
                    "recent_runs": runs[:10],
                }
            ts_repo.close()
        except Exception as exc:
            result["execution_layer"] = {"status": "error", "error": str(exc)}

        # Gap analysis
        gaps = []
        config_count = result.get("config_layer", {}).get("count", 0)
        mapping_count = result.get("mapping_layer", {}).get("count", 0)
        exec_count = result.get("execution_layer", {}).get("total_runs", 0)

        if config_count > 0 and exec_count == 0:
            gaps.append("Jobs are configured but no recent processing found")
        if mapping_count > 0 and exec_count == 0:
            gaps.append("Deal mappings exist but no recent processing found")
        if exec_count > 0 and config_count == 0:
            gaps.append("Processing runs found but no matching job configuration")
        if config_count == 0 and mapping_count == 0 and exec_count == 0:
            gaps.append("No configuration, mappings, or processing found for this query")

        exec_health = result.get("execution_layer", {}).get("health_score", 0)
        if exec_health < 90 and exec_count > 0:
            gaps.append(f"Processing health is {exec_health}% — below 90% threshold")

        result["gaps"] = gaps

        # Overall health score
        scores = []
        if config_count > 0:
            scores.append(100)
        if mapping_count > 0:
            scores.append(100)
        if exec_count > 0:
            scores.append(exec_health)
        result["health_score"] = round(sum(scores) / len(scores), 1) if scores else 0.0

        response.data = result
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def cmd_staging_search(args: argparse.Namespace) -> CliResponse:
    """UC-08: General-purpose tblTemplateStaging search."""
    response = CliResponse(success=True, command="staging_search")
    repo = None
    try:
        repo = _ts_repo_from_args(args)

        filters_json = getattr(args, "filters", None)
        limit = getattr(args, "limit", 50) or 50
        days = getattr(args, "days", None)
        start_date = getattr(args, "start_date", None)
        end_date = getattr(args, "end_date", None)
        query = getattr(args, "query", "") or ""
        filters = _normalise_staging_filters(filters_json)

        if filters or days is not None or start_date or end_date or not query:
            results = repo.advanced_search(
                filters=filters,
                query=query or None,
                days=days,
                start_date=start_date,
                end_date=end_date,
                limit=int(limit),
            )
            query_desc = query or "(all recent staging rows)"
        else:
            results = repo.search(query)
            results = _filter_staging_rows_by_days(results, days)[: int(limit)]
            query_desc = query

        summarised = [_summarise_staging_record(row) for row in results]
        response.data = {
            "query": query_desc,
            "filters": filters,
            "period": {
                "days": days,
                "start_date": start_date,
                "end_date": end_date,
            },
            "results": summarised,
            "match_count": len(summarised),
            "summary": _build_staging_summary(summarised),
        }
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    finally:
        if repo:
            repo.close()
    return response


def cmd_staging_linkage(args: argparse.Namespace) -> CliResponse:
    """Cross-link staging rows to jobs and deals for deterministic UX."""
    response = CliResponse(success=True, command="staging_linkage")
    repo = None
    deal_repo = None
    try:
        query = getattr(args, "query", "") or ""
        days = getattr(args, "days", 30)
        limit = getattr(args, "limit", 25) or 25

        repo = _ts_repo_from_args(args)
        results = repo.advanced_search(query=query or None, days=days, limit=int(limit))
        if not results and query:
            results = _filter_staging_rows_by_days(repo.search(query), days)[: int(limit)]

        summarised = [_summarise_staging_record(row) for row in results]
        reference_jobs, jobs_source = _collect_staging_reference_jobs(args)

        linked_jobs: List[Dict] = []
        linked_job_names = set()
        records_with_context = []
        missing_templates = set()

        for row in summarised:
            matched_jobs = _match_staging_jobs_for_record(reference_jobs, row)
            if not matched_jobs:
                template_name = row.get("TemplateName")
                if template_name:
                    missing_templates.add(template_name)

            for job in matched_jobs:
                job_name = job.get("job_name") or job.get("name")
                xml_type = job.get("xml_type") or "email"
                key = (xml_type, job_name)
                if key in linked_job_names:
                    continue
                linked_job_names.add(key)
                linked_jobs.append(job)

            enriched = dict(row)
            enriched["linked_jobs"] = [
                {
                    "job_name": job.get("job_name") or job.get("name"),
                    "xml_type": job.get("xml_type") or "email",
                    "scrubber": job.get("scrubber") or job.get("template"),
                    "servicer_id": job.get("servicer_id"),
                }
                for job in matched_jobs[:5]
            ]
            records_with_context.append(enriched)

        linked_deals: List[Dict] = []
        servicer_summaries: List[Dict] = []
        servicer_ids = sorted({row.get("ServicerID") for row in summarised if row.get("ServicerID") not in (None, "")})
        dids = {str(row.get("DID")).strip() for row in summarised if str(row.get("DID") or "").strip()}

        if servicer_ids or dids:
            deal_repo = _repo_from_args(args)
            for servicer_id in servicer_ids:
                deals = deal_repo.get_deals_by_company(int(servicer_id))
                linked_deals.extend(deals)
                servicer_summaries.append({
                    "servicer_id": servicer_id,
                    "deal_count": len(deals),
                })

        linked_deals = _dedupe_deal_rows(linked_deals)
        if dids:
            linked_deals = [
                row for row in linked_deals
                if str(row.get("DID") or row.get("did") or "").strip() in dids
                or not dids
            ] or linked_deals

        response.data = {
            "query": query,
            "period_days": days,
            "match_count": len(records_with_context),
            "records": records_with_context,
            "summary": _build_staging_summary(records_with_context),
            "linked_jobs": linked_jobs,
            "linked_job_count": len(linked_jobs),
            "job_context": _build_staging_jobs_context(linked_jobs),
            "linked_deals": linked_deals,
            "linked_deal_count": len(linked_deals),
            "servicer_summaries": servicer_summaries,
            "missing_templates": sorted(missing_templates),
            "data_source": {
                "staging": "tblTemplateStaging",
                "jobs": jobs_source,
                "deals": "tblExternalDIDRef" if (servicer_ids or dids) else "unavailable",
            },
        }
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    finally:
        if repo:
            repo.close()
        if deal_repo:
            deal_repo.close()
    return response


def cmd_staging_audit(args: argparse.Namespace) -> CliResponse:
    """Audit staging coverage against configured jobs and deal mappings."""
    response = CliResponse(success=True, command="staging_audit")
    repo = None
    deal_repo = None
    try:
        days = getattr(args, "days", 30)
        limit = getattr(args, "limit", 100) or 100
        reference_jobs, jobs_source = _collect_staging_reference_jobs(args)

        repo = _ts_repo_from_args(args)
        distinct_templates = repo.get_distinct_templates(days=days)
        process_level_runs = [_summarise_staging_record(row) for row in repo.get_recent_process_level_runs(days=days, limit=int(limit))]
        filepath_samples = [_summarise_staging_record(row) for row in repo.get_recent_filepath_samples(days=days, limit=int(limit))]

        templates_without_jobs = []
        staging_template_names = set()
        for row in distinct_templates:
            template_name = row.get("TemplateName") or ""
            if not template_name:
                continue
            staging_template_names.add(template_name)
            if not _match_jobs_by_scrubber(reference_jobs, template_name):
                templates_without_jobs.append({
                    "TemplateName": template_name,
                    "run_count": row.get("run_count", 0),
                })

        jobs_without_recent_runs = []
        for job in reference_jobs:
            scrubber = str(job.get("scrubber") or job.get("template") or "").strip()
            if scrubber and scrubber not in staging_template_names:
                jobs_without_recent_runs.append({
                    "job_name": job.get("job_name") or job.get("name"),
                    "xml_type": job.get("xml_type") or "email",
                    "scrubber": scrubber,
                    "servicer_id": job.get("servicer_id"),
                })

        filepath_gaps = []
        unmapped_servicers = []
        checked_servicers = set()
        deal_repo = _repo_from_args(args)

        for row in filepath_samples:
            matched_jobs = _match_staging_jobs_for_record(reference_jobs, row)
            if not matched_jobs:
                filepath_gaps.append({
                    "TemplateProcessID": row.get("TemplateProcessID"),
                    "TemplateName": row.get("TemplateName"),
                    "FilePath": row.get("FilePath"),
                    "source_type": row.get("source_type"),
                    "DataSource": row.get("DataSource"),
                })

            servicer_id = row.get("ServicerID")
            if servicer_id in (None, "") or servicer_id in checked_servicers:
                continue
            checked_servicers.add(servicer_id)
            deals = deal_repo.get_deals_by_company(int(servicer_id))
            if not deals:
                unmapped_servicers.append({
                    "ServicerID": servicer_id,
                    "TemplateName": row.get("TemplateName"),
                    "sample_filepath": row.get("FilePath"),
                })

        response.data = {
            "period_days": days,
            "reference_job_count": len(reference_jobs),
            "reference_job_source": jobs_source,
            "staging_template_count": len(distinct_templates),
            "templates_without_jobs": templates_without_jobs[:50],
            "jobs_without_recent_runs": jobs_without_recent_runs[:50],
            "recent_process_level_runs": process_level_runs[:50],
            "filepath_gaps": filepath_gaps[:50],
            "unmapped_servicers": unmapped_servicers[:50],
            "summary": {
                "templates_without_jobs": len(templates_without_jobs),
                "jobs_without_recent_runs": len(jobs_without_recent_runs),
                "process_level_runs": len(process_level_runs),
                "filepath_gaps": len(filepath_gaps),
                "unmapped_servicers": len(unmapped_servicers),
            },
            "data_source": {
                "staging": "tblTemplateStaging",
                "jobs": jobs_source,
                "deals": "tblExternalDIDRef",
            },
        }
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    finally:
        if repo:
            repo.close()
        if deal_repo:
            deal_repo.close()
    return response


def cmd_rebuild_db(args: argparse.Namespace) -> CliResponse:
    """Rebuild the SQLite job-config cache from the XML settings file(s)."""
    from backend.db.xml_index import XmlJobIndex

    response = CliResponse(success=True, command="rebuild_db")
    try:
        with XmlJobIndex(args.cache_db_path) as index:
            rebuilt: Dict[str, int] = {}

            if args.xml_type in ("email", "all"):
                rebuild_result = index.rebuild(args.settings_path, "email")
                rebuilt["email_jobs"] = rebuild_result.get("email_jobs_loaded", 0)

            if args.xml_type in ("sftp", "all"):
                sftp_path = getattr(args, "sftp_settings_path", None)
                if sftp_path:
                    rebuild_result = index.rebuild(sftp_path, "sftp")
                    rebuilt["sftp_jobs"] = rebuild_result.get("sftp_jobs_loaded", 0)
                elif args.xml_type == "sftp":
                    response.add_warning("--sftp-settings-path not provided; nothing rebuilt.")

            response.data = {"rebuilt": rebuilt, "db_path": args.cache_db_path}
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    return response


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="frp-agent",
        description="FRP Agent CLI — JSON-based command interface for the FRP backend.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── search_jobs ──────────────────────────────────────────────── #
    sp = subparsers.add_parser("search_jobs", help="Search for jobs in Settings.xml")
    sp.add_argument("--query", required=True, help="Free-text search query")
    sp.add_argument(
        "--xml-type",
        default="all",
        choices=["email", "sftp", "all"],
        help="Which XML settings to search (default: all)",
    )
    sp.add_argument("--settings-path", required=True, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")

    # ── job_detail ───────────────────────────────────────────────── #
    sp = subparsers.add_parser("job_detail", help="Full detail for a single job with deal cross-ref")
    sp.add_argument("--job-name", required=True, help="Exact job name")
    sp.add_argument("--settings-path", required=True, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"])
    sp.add_argument("--db-mode", default=None, help="Database mode for deal cross-ref (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")

    # ── deal_lookup ──────────────────────────────────────────────── #
    sp = subparsers.add_parser("deal_lookup", help="Find jobs serving a deal / CompanyID")
    sp.add_argument("--query", required=True, help="Deal name, ImportDID keyword, or CompanyID")
    sp.add_argument("--settings-path", required=True, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"])
    sp.add_argument("--lookup-type", default="auto", choices=["auto", "did", "keyword", "company", "servicer"], help="Deterministic lookup mode for tblExternalDIDRef queries")
    sp.add_argument("--filters-json", default=None, help="Optional JSON array of deterministic deal filters, e.g. [{\"type\":\"keyword\",\"value\":\"KF169\"}]")
    sp.add_argument("--db-mode", required=True, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--cache-db-path", default=None, help="Path to the SQLite job-config cache database")

    # ── validate_xml ─────────────────────────────────────────────── #
    sp = subparsers.add_parser("validate_xml", help="Validate a Settings.xml file")
    sp.add_argument(
        "--xml-type",
        default="email",
        choices=["email", "sftp"],
        help="Type of XML file (default: email)",
    )
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument("--db-mode", default=None, help="Database mode for cross-validation (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name (from VS Code settings)")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name (from VS Code settings)")

    # ── sync_logs ────────────────────────────────────────────────── #
    sp = subparsers.add_parser("sync_logs", help="Sync log files into the SQLite index")
    sp.add_argument("--log-folder", default=None, help="Folder containing email .log files")
    sp.add_argument("--sftp-log-folder", default=None, help="Folder containing SFTP .log files")
    sp.add_argument("--db-path", required=True, help="Path to the SQLite index database")
    sp.add_argument(
        "--retention-months",
        type=int,
        default=3,
        help="Months of log data to retain (default: 3)",
    )

    # ── servicer_dossier ─────────────────────────────────────────── #
    sp = subparsers.add_parser("servicer_dossier", help="Build a servicer/job dossier")
    sp.add_argument("--query", default=None, help="Servicer ID or job name to look up")
    sp.add_argument("--servicer-id", type=int, default=None, help="Servicer (company) ID")
    sp.add_argument("--job-name", default=None, help="Job name to look up")
    sp.add_argument("--settings-path", required=True, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--db-mode", default="mysql", help="Database mode (default: mysql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name (from VS Code settings)")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name (from VS Code settings)")
    sp.add_argument("--log-db-path", default=None, help="Path to the SQLite log index database")

    # ── list_backups ─────────────────────────────────────────────── #
    sp = subparsers.add_parser("list_backups", help="List backup files for Settings.xml")
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument(
        "--xml-type",
        default="email",
        choices=["email", "sftp"],
        help="XML type (default: email)",
    )

    # ── save_xml ─────────────────────────────────────────────────── #
    sp = subparsers.add_parser("save_xml", help="Re-save Settings.xml with a backup")
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument(
        "--xml-type",
        default="email",
        choices=["email", "sftp"],
        help="XML type (default: email)",
    )

    # ── create_job (Phase 2) ──────────────────────────────────────── #
    sp = subparsers.add_parser("create_job", help="Create a new job from template")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    sp.add_argument("--template-job", required=True, help="Name of template job to copy")
    sp.add_argument("--name", required=True, help="Name for the new job")
    sp.add_argument("--servicer-id", default=None)
    sp.add_argument("--mailbox", default=None)
    sp.add_argument("--import-did", default=None)
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")

    # ── next_servicer_id ─────────────────────────────────────────── #
    sp = subparsers.add_parser(
        "next_servicer_id",
        help="Find the next unused ServicerID >= base_id+1 across email and SFTP jobs",
    )
    sp.add_argument("--base-id", required=True, type=int,
                    help="ServicerID of the template / series anchor (e.g. 6007)")
    sp.add_argument("--cache-db-path", required=True,
                    help="Path to SQLite cache database")

    # ── edit_job (Phase 2) ────────────────────────────────────────── #
    sp = subparsers.add_parser("edit_job", help="Edit a field on an existing job")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    sp.add_argument("--job-name", required=True)
    sp.add_argument("--field", required=True)
    sp.add_argument("--value", required=True)
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")

    # ── clone_prepare / clone_preview / clone_apply ────────────────── #
    sp = subparsers.add_parser("clone_prepare", help="Prepare a deterministic clone by ServicerID")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--sftp-settings-path", default=None)
    sp.add_argument("--source-servicer-id", required=True, type=int)

    sp = subparsers.add_parser("clone_preview", help="Preview a deterministic clone by ServicerID")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--sftp-settings-path", default=None)
    sp.add_argument("--source-servicer-id", required=True, type=int)
    sp.add_argument("--clone-job-name", required=True)
    sp.add_argument("--assigned-servicer-id", required=True, type=int)
    sp.add_argument("--overrides-json", default=None)

    sp = subparsers.add_parser("clone_apply", help="Apply a deterministic clone by ServicerID")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--sftp-settings-path", default=None)
    sp.add_argument("--source-servicer-id", required=True, type=int)
    sp.add_argument("--clone-job-name", required=True)
    sp.add_argument("--assigned-servicer-id", required=True, type=int)
    sp.add_argument("--overrides-json", default=None)
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")

    # ── template_inventory (Phase 2) ──────────────────────────────── #
    sp = subparsers.add_parser("template_inventory", help="Discover template patterns")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    sp.add_argument("--filter", default=None)

    # ── coverage_gaps (Phase 2) ───────────────────────────────────── #
    sp = subparsers.add_parser("coverage_gaps", help="Analyze coverage gaps")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--db-mode", default="mysql", choices=["mysql", "mssql"])
    sp.add_argument("--secrets-path", required=True)
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--servicer-id", default="all")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── orphan_detection (Phase 2) ────────────────────────────────── #
    sp = subparsers.add_parser("orphan_detection", help="Detect orphaned jobs")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--db-mode", default="mysql", choices=["mysql", "mssql"])
    sp.add_argument("--secrets-path", required=True)
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── collision_detection (Phase 2) ─────────────────────────────── #
    sp = subparsers.add_parser("collision_detection", help="Detect ImportDID collisions")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--db-mode", default="mysql", choices=["mysql", "mssql"])
    sp.add_argument("--secrets-path", required=True)
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── xml_diff (Phase 2) ────────────────────────────────────────── #
    sp = subparsers.add_parser("xml_diff", help="Diff Settings.xml against backup")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--backup-file", default=None)
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── rollback_xml (Phase 2) ────────────────────────────────────── #
    sp = subparsers.add_parser("rollback_xml", help="Rollback Settings.xml to backup")
    sp.add_argument("--settings-path", required=True)
    sp.add_argument("--backup-file", required=True)
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── log_deal_activity (Phase 3) ───────────────────────────────── #
    sp = subparsers.add_parser("log_deal_activity", help="Query deal activity from log index")
    sp.add_argument("--did", required=True, help="DID name or number to search for")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")
    sp.add_argument("--db-mode", default=None, help="Database mode for DID resolution (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── log_did_failures (Phase 3) ────────────────────────────────── #
    sp = subparsers.add_parser("log_did_failures", help="Aggregate DID-mapping failures")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--job-filter", default=None, help="Filter failures by job name")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")

    # ── log_job_health (Phase 3) ──────────────────────────────────── #
    sp = subparsers.add_parser("log_job_health", help="Compute job health metrics")
    sp.add_argument("--job-name", required=True, help="Job name to analyse")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")

    # ── log_daily_summary (Phase 3) ───────────────────────────────── #
    sp = subparsers.add_parser("log_daily_summary", help="One-day operational summary")
    sp.add_argument("--date", default=None, help="ISO date (YYYY-MM-DD), defaults to today")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")

    # ── triage_verify (Phase 3) ───────────────────────────────────── #
    sp = subparsers.add_parser("triage_verify", help="Verify a .msg file against existing jobs")
    sp.add_argument("--msg-path", required=True, help="Path to the .msg file")
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--log-dir", default=None, help="Path to log directory for execution cross-reference")

    # ── triage_match (Phase 3) ────────────────────────────────────── #
    sp = subparsers.add_parser("triage_match", help="Match an email to existing jobs")
    sp.add_argument("--msg-path", default=None, help="Path to a .msg file")
    sp.add_argument("--sender", default=None, help="Sender email address")
    sp.add_argument("--subject", default=None, help="Email subject line")
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])

    # ── triage_new (Phase 3) ──────────────────────────────────────── #
    sp = subparsers.add_parser("triage_new", help="Analyze email for new-job creation")
    sp.add_argument("--msg-path", required=True, help="Path to the .msg file")
    sp.add_argument("--settings-path", required=True, help="Path to the Settings.xml")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp"])
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── status ───────────────────────────────────────────────────── #
    subparsers.add_parser("status", help="Show runtime status information")

    # ── log_trends (Phase 4) ──────────────────────────────────────── #
    sp = subparsers.add_parser("log_trends", help="Timeline trend analysis")
    sp.add_argument("--days", type=int, default=14, help="Number of days to analyse (default: 14)")
    sp.add_argument("--job", default=None, help="Filter to a specific job name")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")

    # ── log_performance (Phase 4) ─────────────────────────────────── #
    sp = subparsers.add_parser("log_performance", help="Job performance benchmarking")
    sp.add_argument(
        "--sort",
        default="success_rate",
        choices=["success_rate", "total_files", "total_errors", "avg_files_per_run", "last_run"],
        help="Sort key (default: success_rate)",
    )
    sp.add_argument("--ascending", type=bool, default=True, help="Sort ascending (default: True)")
    sp.add_argument("--top", type=int, default=None, help="Limit to top N entries")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")
    sp.add_argument("--settings-path", default=None, help="Path to Settings.xml (optional)")

    # ── log_search ────────────────────────────────────────────────── #
    sp = subparsers.add_parser("log_search", help="Search log events by job name or keyword")
    sp.add_argument("--query", default="", help="Optional free-text search term (partial job name match)")
    sp.add_argument("--event-type", default=None, choices=["errors", "activity"],
                    help="Legacy filter mode: 'errors' for error details, 'activity' for actionable events only")
    sp.add_argument("--mode", default="summary", choices=["summary", "events", "details", "errors", "activity", "detail", "email", "emails"],
                    help="Response mode (default: summary)")
    sp.add_argument("--job-name", default=None, help="Structured job-name filter")
    sp.add_argument("--filters", default=None, help="JSON object/list of structured log filters")
    sp.add_argument("--days", type=int, default=None, help="Look-back window in days")
    sp.add_argument("--start-date", default=None, help="ISO start date/time")
    sp.add_argument("--end-date", default=None, help="ISO end date/time")
    sp.add_argument("--limit", type=int, default=50, help="Max events to return (default: 50)")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")

    # ── log_linkage ───────────────────────────────────────────────── #
    sp = subparsers.add_parser("log_linkage", help="Cross-link log evidence to jobs, deals, and staging")
    sp.add_argument("--query", required=True, help="Job name, DID, servicer, or free-text log clue")
    sp.add_argument("--filters", default=None, help="JSON object/list of structured log filters")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--start-date", default=None, help="ISO start date/time")
    sp.add_argument("--end-date", default=None, help="ISO end date/time")
    sp.add_argument("--limit", type=int, default=25, help="Max linked rows to return (default: 25)")
    sp.add_argument("--db-path", default="frp_logs.db", help="Path to the SQLite log database")
    sp.add_argument("--settings-path", default=None, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--cache-db-path", default=None, help="Path to the SQLite XML cache")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"])
    sp.add_argument("--db-mode", default=None, help="Database mode for deal/staging lookups (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to the DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── analyze_consolidation (Phase 4) ───────────────────────────── #
    sp = subparsers.add_parser("analyze_consolidation", help="Job consolidation analysis")
    sp.add_argument("--type", default="all", choices=["email", "sftp", "all"], help="XML type filter")
    sp.add_argument("--settings-path", required=True, help="Path to Settings.xml")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── analyze_impact (Phase 4) ──────────────────────────────────── #
    sp = subparsers.add_parser("analyze_impact", help="Change impact simulation")
    sp.add_argument(
        "--change-type",
        required=True,
        choices=["delete_job", "rename_did", "change_filter", "move_servicer"],
        help="Type of change to simulate",
    )
    sp.add_argument("--target-job", default=None, help="Job name (for delete/change_filter)")
    sp.add_argument("--target-did", default=None, help="ImportDID keyword (for rename_did)")
    sp.add_argument("--target-company-id", type=int, default=None, help="CompanyID (for move_servicer)")
    sp.add_argument("--new-value", default=None, help="New value for the change")
    sp.add_argument("--raw-description", default="", help="Original natural-language description")
    sp.add_argument("--settings-path", required=True, help="Path to Settings.xml")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--db-path", default=None, help="Path to SQLite log database")

    # ── analyze_health (Phase 4) ──────────────────────────────────── #
    sp = subparsers.add_parser("analyze_health", help="Full system health check")
    sp.add_argument("--type", default="all", choices=["email", "sftp", "all"], help="XML type filter")
    sp.add_argument("--settings-path", default=None, help="Path to Settings.xml")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")
    sp.add_argument("--db-path", default=None, help="Path to SQLite log database")

    # ── template_status (Phase 5) ─────────────────────────────────── #
    sp = subparsers.add_parser("template_status", help="Check processing status for a deal/template")
    sp.add_argument("--query", required=True, help="Template name, DID, or keyword")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--limit", type=int, default=10, help="Max rows to return (default: 10)")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── processing_history (Phase 5) ──────────────────────────────── #
    sp = subparsers.add_parser("processing_history", help="Full processing history for a deal")
    sp.add_argument("--query", required=True, help="DID, ServicerID, or TemplateName")
    sp.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    sp.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD)")
    sp.add_argument("--limit", type=int, default=50, help="Max rows to return (default: 50)")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── failure_analysis (Phase 5) ────────────────────────────────── #
    sp = subparsers.add_parser("failure_analysis", help="Analyze processing failures")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--template", default=None, help="Optional template name filter")
    sp.add_argument("--did", default=None, help="Optional DID filter")
    sp.add_argument("--detail", action="store_true", help="Show individual failure records")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── source_trace (Phase 5) ────────────────────────────────────── #
    sp = subparsers.add_parser("source_trace", help="Trace file origin to processing")
    sp.add_argument("--filepath", required=True, help="Full or partial file path to trace")
    sp.add_argument("--limit", type=int, default=10, help="Max rows to return (default: 10)")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── manual_queue_report (Phase 5) ─────────────────────────────── #
    sp = subparsers.add_parser("manual_queue_report", help="Manual vs automated processing breakdown")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--template", default=None, help="Optional template filter")
    sp.add_argument("--servicer-id", default=None, help="Optional servicer ID filter")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── processing_duration (Phase 5) ─────────────────────────────── #
    sp = subparsers.add_parser("processing_duration", help="Processing time analysis")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--template", default=None, help="Optional template name filter")
    sp.add_argument("--sort", default="avg_seconds", choices=["avg_seconds", "max_seconds", "total_runs"],
                    help="Sort key (default: avg_seconds)")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── deal_pipeline (Phase 5) ───────────────────────────────────── #
    sp = subparsers.add_parser("deal_pipeline", help="End-to-end pipeline visibility")
    sp.add_argument("--query", required=True, help="DID, ServicerID, or TemplateName")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--settings-path", default=None, help="Path to Settings.xml")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── staging_search (Phase 5) ──────────────────────────────────── #
    sp = subparsers.add_parser("staging_search", help="Search tblTemplateStaging records")
    sp.add_argument("--query", default="", help="Search term: TemplateProcessID, DID, TemplateName, or FilePath")
    sp.add_argument("--filters", default=None, help='JSON object of column=value filters, e.g. {"TemplateName":"QueueCMBS","DID":"FREMF 2026-KF169"}')
    sp.add_argument("--days", type=int, default=None, help="Optional look-back window in days")
    sp.add_argument("--start-date", default=None, help="Start date in YYYY-MM-DD format")
    sp.add_argument("--end-date", default=None, help="End date in YYYY-MM-DD format")
    sp.add_argument("--limit", type=int, default=50, help="Max rows to return (default: 50)")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── staging_linkage ──────────────────────────────────────────────── #
    sp = subparsers.add_parser("staging_linkage", help="Link staging rows to jobs and deals")
    sp.add_argument("--query", required=True, help="Template name, DID, filepath token, or ServicerID-related text")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--limit", type=int, default=25, help="Max staging rows to inspect (default: 25)")
    sp.add_argument("--settings-path", default=None, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"], help="Which XML settings to inspect")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── staging_audit ────────────────────────────────────────────────── #
    sp = subparsers.add_parser("staging_audit", help="Audit staging coverage and linkage gaps")
    sp.add_argument("--days", type=int, default=30, help="Look-back window in days (default: 30)")
    sp.add_argument("--limit", type=int, default=100, help="Max recent staging rows to sample per audit section")
    sp.add_argument("--settings-path", default=None, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--cache-db-path", default=None, help="Path to SQLite cache database")
    sp.add_argument("--xml-type", default="all", choices=["email", "sftp", "all"], help="Which XML settings to inspect")
    sp.add_argument("--db-mode", default=None, help="Database mode (mysql|mssql)")
    sp.add_argument("--secrets-path", default=None, help="Path to DB secrets JSON file")
    sp.add_argument("--mssql-server", default=None, help="MSSQL server name")
    sp.add_argument("--mssql-database", default=None, help="MSSQL database name")

    # ── rebuild_db (Phase 6) ──────────────────────────────────────── #
    sp = subparsers.add_parser("rebuild_db", help="Rebuild SQLite cache from XML settings")
    sp.add_argument("--cache-db-path", required=True, help="Path to SQLite cache database")
    sp.add_argument("--settings-path", required=True, help="Path to the email Settings.xml")
    sp.add_argument("--sftp-settings-path", default=None, help="Path to the SFTP Settings.xml")
    sp.add_argument("--xml-type", default="email", choices=["email", "sftp", "all"],
                    help="Which XML to rebuild (default: email)")

    return parser


# ===================================================================== #
#  Persistent server mode (stdin/stdout JSON-RPC-like)
# ===================================================================== #

def _run_server() -> None:
    """Read JSON command objects from stdin, dispatch, write JSON responses.

    Each request is a single JSON line on stdin::

        {"command": "search_jobs", "args": {"query": "tpmt", "settings_path": "..."}}

    The response is a single JSON line on stdout (the full CliResponse).
    A special ``{"command": "__ping__"}`` is answered immediately so the
    client can verify the process is alive.  ``{"command": "__exit__"}``
    terminates the loop.
    """
    logger.info("Server mode started — waiting for JSON commands on stdin")

    # Signal readiness to the extension (single line, flushed)
    sys.stdout.write('{"status":"ready"}\n')
    sys.stdout.flush()

    arg_parser = _build_parser()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _server_respond({"status": "error", "error": f"Bad JSON: {exc}"})
            continue

        command = request.get("command", "")

        # Built-in meta commands
        if command == "__ping__":
            _server_respond({"status": "ok", "pong": True})
            continue
        if command == "__exit__":
            _server_respond({"status": "ok", "exiting": True})
            break

        handler = _COMMAND_DISPATCH.get(command)
        if handler is None:
            _server_respond({"status": "error", "error": f"Unknown command: {command}"})
            continue

        # Build an argv list from the request's args dict and parse it
        argv = [command]
        for key, value in request.get("args", {}).items():
            flag = "--" + key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    argv.append(flag)
            else:
                argv.append(flag)
                argv.append(str(value))

        try:
            args = arg_parser.parse_args(argv)
        except SystemExit:
            _server_respond({"status": "error", "error": f"Bad args for {command}: {argv}"})
            continue

        start = time.perf_counter()
        try:
            response = handler(args)
        except Exception as exc:
            logger.exception("Unhandled exception in command '%s'", command)
            response = CliResponse(
                success=False,
                command=command,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        response.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        _server_respond(response.to_dict())

    logger.info("Server mode exiting")


def _server_respond(obj: dict) -> None:
    """Write a single JSON line to stdout and flush."""
    json.dump(obj, sys.stdout, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


# ===================================================================== #
#  Main entry point
# ===================================================================== #

_COMMAND_DISPATCH: Dict[str, Callable[[argparse.Namespace], CliResponse]] = {
    "search_jobs": cmd_search_jobs,
    "job_detail": cmd_job_detail,
    "deal_lookup": cmd_deal_lookup,
    "validate_xml": cmd_validate_xml,
    "sync_logs": cmd_sync_logs,
    "servicer_dossier": cmd_servicer_dossier,
    "list_backups": cmd_list_backups,
    "save_xml": cmd_save_xml,
    "status": cmd_status,
    "create_job": cmd_create_job,
    "edit_job": cmd_edit_job,
    "clone_prepare": cmd_clone_prepare,
    "clone_preview": cmd_clone_preview,
    "clone_apply": cmd_clone_apply,
    "template_inventory": cmd_template_inventory,
    "coverage_gaps": cmd_coverage_gaps,
    "orphan_detection": cmd_orphan_detection,
    "collision_detection": cmd_collision_detection,
    "xml_diff": cmd_xml_diff,
    "rollback_xml": cmd_rollback_xml,
    "log_deal_activity": cmd_log_deal_activity,
    "log_did_failures": cmd_log_did_failures,
    "log_job_health": cmd_log_job_health,
    "log_daily_summary": cmd_log_daily_summary,
    "triage_verify": cmd_triage_verify,
    "triage_match": cmd_triage_match,
    "triage_new": cmd_triage_new,
    "log_trends": cmd_log_trends,
    "log_performance": cmd_log_performance,
    "log_search": cmd_log_search,
    "log_linkage": cmd_log_linkage,
    "analyze_consolidation": cmd_analyze_consolidation,
    "analyze_impact": cmd_analyze_impact,
    "analyze_health": cmd_analyze_health,
    # Phase 5 — tblTemplateStaging commands
    "template_status": cmd_template_status,
    "processing_history": cmd_processing_history,
    "failure_analysis": cmd_failure_analysis,
    "source_trace": cmd_source_trace,
    "manual_queue_report": cmd_manual_queue_report,
    "processing_duration": cmd_processing_duration,
    "deal_pipeline": cmd_deal_pipeline,
    "staging_search": cmd_staging_search,
    "staging_linkage": cmd_staging_linkage,
    "staging_audit": cmd_staging_audit,
    # Phase 6 — SQLite cache
    "rebuild_db": cmd_rebuild_db,
    "next_servicer_id": cmd_next_servicer_id,
}


def main() -> None:
    """Parse arguments, dispatch the requested command, and print JSON."""
    _configure_logging()

    # ── Persistent server mode ──────────────────────────────────── #
    if "--server" in sys.argv:
        _run_server()
        return

    arg_parser = _build_parser()
    args = arg_parser.parse_args()

    handler = _COMMAND_DISPATCH.get(args.command)
    if handler is None:
        # Should never happen due to argparse, but guard anyway.
        sys.stderr.write(f"Unknown command: {args.command}\n")
        sys.exit(1)

    start = time.perf_counter()

    try:
        response = handler(args)
    except Exception as exc:
        logger.exception("Unhandled exception in command '%s'", args.command)
        response = CliResponse(
            success=False,
            command=args.command,
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    response.elapsed_ms = round(elapsed_ms, 2)

    json.dump(response.to_dict(), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
