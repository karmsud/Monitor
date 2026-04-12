"""Data-access layer for the tblTemplateStaging table.

Provides read-only helpers used by the CLI and agent layers to query
template processing history — scrubber runs, results, errors, etc.

In US Bank production the table lives in a separate database and must be
referenced as ``ToolsHub.ToolsHub.dbo.tblTemplateStaging`` when the ODBC
connection targets ``Servicing``.  In the local MySQL dev environment the
bare table name ``tblTemplateStaging`` is used.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from backend.db.connection import get_connection
from backend.db import queries

logger = logging.getLogger("frp.db.template_staging_repo")


_EXECUTION_TS_SQL = queries.TEMPLATE_STAGING_EXECUTION_TS


class TemplateStagingRepository:
    """Repository wrapping parameterised queries against tblTemplateStaging."""

    # ------------------------------------------------------------------ #
    # Construction / lifecycle
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        prod_mode: bool = False,
        secrets_path: Optional[str] = None,
        mssql_server: Optional[str] = None,
        mssql_database: Optional[str] = None,
    ) -> None:
        """Open a database connection via the shared factory.

        Parameters
        ----------
        prod_mode:
            ``True`` → MSSQL (production), ``False`` → MySQL (dev).
        secrets_path:
            Optional override for the JSON secrets file.
        mssql_server:
            MSSQL server name from VS Code ``frpAgent.mssqlServer`` setting.
        mssql_database:
            MSSQL database name from VS Code ``frpAgent.mssqlDatabase`` setting.
        """
        self._prod_mode = prod_mode
        self._conn = get_connection(
            prod_mode=prod_mode,
            secrets_path=secrets_path,
            mssql_server=mssql_server,
            mssql_database=mssql_database,
        )
        logger.info(
            "TemplateStagingRepository initialised (prod_mode=%s)", prod_mode,
        )

    # ------------------------------------------------------------------ #
    # SQL dialect adaptation (MySQL ↔ MSSQL)
    # ------------------------------------------------------------------ #

    # Regex for `LIMIT <literal>` at the end of a query
    _RE_LIMIT_LITERAL = re.compile(r'\bLIMIT\s+(\d+)\s*$', re.IGNORECASE)
    # Regex for `LIMIT ?` (parameterised) at the end of a query
    _RE_LIMIT_PARAM = re.compile(r'\bLIMIT\s+\?\s*$', re.IGNORECASE)

    def _adapt_sql(self, sql: str, params: tuple = ()) -> tuple:
        """Rewrite a MySQL query for MSSQL when *_prod_mode* is True.

        Adaptations performed:
        - ``tblTemplateStaging`` → ``ToolsHub.ToolsHub.dbo.tblTemplateStaging``
        - ``LIMIT N``  → ``TOP N`` (literal)
        - ``LIMIT ?``  → ``TOP ?`` (parameterised — moves the param)
        - ``GROUP_CONCAT(...)`` → ``STRING_AGG(...)``
        - ``TIMESTAMPDIFF(SECOND, a, b)`` → ``DATEDIFF(SECOND, a, b)``
        - ``SEPARATOR '...'`` → ``', '`` inside STRING_AGG
        """
        if not self._prod_mode:
            return sql, params

        # Table name
        sql = sql.replace('tblTemplateStaging', 'ToolsHub.ToolsHub.dbo.tblTemplateStaging')

        # TIMESTAMPDIFF → DATEDIFF
        sql = sql.replace('TIMESTAMPDIFF(', 'DATEDIFF(')

        # GROUP_CONCAT(DISTINCT col ORDER BY col SEPARATOR ', ') → STRING_AGG(col, ', ')
        sql = re.sub(
            r"GROUP_CONCAT\(DISTINCT\s+(\w+)\s+ORDER\s+BY\s+\w+\s+SEPARATOR\s+'([^']+)'\)",
            r"STRING_AGG(\1, '\2')",
            sql,
            flags=re.IGNORECASE,
        )

        # LIMIT <literal> → TOP <literal>
        m_lit = self._RE_LIMIT_LITERAL.search(sql)
        if m_lit:
            n = m_lit.group(1)
            sql = self._RE_LIMIT_LITERAL.sub('', sql)
            sql = re.sub(r'\bSELECT\b', f'SELECT TOP {n}', sql, count=1, flags=re.IGNORECASE)
            return sql, params

        # LIMIT ? → TOP ? (remove the trailing param placeholder, add TOP before columns)
        m_param = self._RE_LIMIT_PARAM.search(sql)
        if m_param:
            sql = self._RE_LIMIT_PARAM.sub('', sql)
            sql = re.sub(r'\bSELECT\b', 'SELECT TOP (?)', sql, count=1, flags=re.IGNORECASE)
            # The limit param was last in the tuple — move it to the first position
            if params:
                params_list = list(params)
                limit_val = params_list.pop()  # was the last param
                params = tuple([limit_val] + params_list)

        return sql, params

    def _exec(self, sql: str, params: tuple = ()):
        """Execute *sql* with MSSQL adaptation and return the cursor."""
        adapted_sql, adapted_params = self._adapt_sql(sql, params)
        # Log the actual SQL and params so we can diagnose query issues
        logger.info("SQL  → %s", adapted_sql.strip().replace('\n', ' '))
        logger.info("PARAMS → %s", adapted_params)
        cursor = self._conn.cursor()
        cursor.execute(adapted_sql, adapted_params)
        row_count = cursor.rowcount
        logger.info("ROWS → %s", row_count)
        return cursor

    # ------------------------------------------------------------------ #
    # Helper: row → dict
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rows_to_dicts(cursor) -> List[Dict]:
        """Convert all rows under *cursor* to a list of column-keyed dicts."""
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _cutoff_datetime(days: int) -> str:
        from datetime import datetime, timedelta

        return (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _normalise_range_start(value: str) -> str:
        text = str(value or "").strip()
        if len(text) == 10:
            return f"{text} 00:00:00"
        return text

    @staticmethod
    def _normalise_range_end(value: str) -> str:
        text = str(value or "").strip()
        if len(text) == 10:
            return f"{text} 23:59:59"
        return text

    # ------------------------------------------------------------------ #
    # Public query methods
    # ------------------------------------------------------------------ #

    def get_by_id(self, template_process_id: int) -> Optional[Dict]:
        """Return a single template staging record by its TemplateProcessID."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_BY_ID, (template_process_id,))
        rows = self._rows_to_dicts(cursor)
        cursor.close()
        return rows[0] if rows else None

    def get_by_template_name(self, template_name: str) -> List[Dict]:
        """Return all runs for a given template (scrubber) name."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_BY_TEMPLATE_NAME, (template_name,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_by_did(self, did: str) -> List[Dict]:
        """Return all template runs for an exact DID value."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_BY_DID, (did,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def search_by_did(self, did_pattern: str) -> List[Dict]:
        """Search template runs where ``DID LIKE ?``.

        *did_pattern* should include SQL wildcards, e.g. ``%WB6%``.
        """
        cursor = self._exec(queries.SEARCH_TEMPLATE_STAGING_BY_DID, (did_pattern,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_failures(self) -> List[Dict]:
        """Return all template runs that failed (ResultCode = 1)."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_FAILURES)
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_successes(self) -> List[Dict]:
        """Return all template runs that succeeded (ResultCode = 0)."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_SUCCESSES)
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Return template runs within an execution-time date range.

        Parameters
        ----------
        start_date / end_date:
            ISO date strings, e.g. ``'2021-11-01'``, ``'2021-12-31'``.
        """
        cursor = self._exec(
            queries.GET_TEMPLATE_STAGING_BY_DATE_RANGE,
            (self._normalise_range_start(start_date), self._normalise_range_end(end_date)),
        )
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def search_by_query_and_date_range(
        self, query: str, start_date: str, end_date: str, limit: int = 50,
    ) -> List[Dict]:
        """Search by DID or TemplateName (LIKE) within a date range.

        Pushes all filtering into SQL with a row LIMIT so production
        tables with millions of rows are handled safely.
        """
        pattern = f"%{query}%"
        cursor = self._exec(
            queries.GET_TEMPLATE_STAGING_BY_QUERY_AND_DATE_RANGE,
            (
                pattern,
                pattern,
                self._normalise_range_start(start_date),
                self._normalise_range_end(end_date),
                limit,
            ),
        )
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_summary(self) -> Dict:
        """Return aggregate stats across all template staging records."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_SUMMARY)
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return {
                "total_runs": 0,
                "successes": 0,
                "failures": 0,
                "unique_templates": 0,
                "unique_deals": 0,
            }
        return {
            "total_runs": row[0],
            "successes": row[1],
            "failures": row[2],
            "unique_templates": row[3],
            "unique_deals": row[4],
        }

    def get_summary_by_template(self, template_name: str) -> Dict:
        """Return run stats for a specific template name."""
        cursor = self._exec(queries.GET_TEMPLATE_STAGING_SUMMARY_BY_TEMPLATE, (template_name,))
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return {
                "template_name": template_name,
                "total_runs": 0,
                "successes": 0,
                "failures": 0,
            }
        return {
            "template_name": row[0],
            "total_runs": row[1],
            "successes": row[2],
            "failures": row[3],
        }

    def search_by_filepath(self, filepath_pattern: str) -> List[Dict]:
        """Search template runs where ``FilePath LIKE ?``.

        *filepath_pattern* should include SQL wildcards, e.g. ``%FKMF%``.
        """
        cursor = self._exec(queries.SEARCH_TEMPLATE_STAGING_BY_FILEPATH, (filepath_pattern,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_all_template_names(self) -> List[str]:
        """Return all distinct template names in the staging table."""
        cursor = self._exec(queries.GET_ALL_TEMPLATE_NAMES)
        names = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return names

    def search(self, query: str) -> List[Dict]:
        """Flexible search: tries TemplateProcessID, DID, TemplateName, then FilePath.

        Handles queries like '74', 'TPMT_SPS', 'WB6 GT 2020-1', 'FKMF', etc.
        """
        # Try as TemplateProcessID
        try:
            tid = int(query)
            result = self.get_by_id(tid)
            if result:
                return [result]
        except ValueError:
            pass

        # Try exact DID
        results = self.get_by_did(query)
        if results:
            return results

        # Try exact template name
        results = self.get_by_template_name(query)
        if results:
            return results

        # Try DID pattern
        results = self.search_by_did(f"%{query}%")
        if results:
            return results

        # Try filepath pattern
        return self.search_by_filepath(f"%{query}%")

    # ------------------------------------------------------------------ #
    # Generic multi-column filtered search
    # ------------------------------------------------------------------ #

    # Whitelist of columns that callers may filter on.
    _VALID_COLUMNS = frozenset({
        "TemplateProcessID", "TemplateName", "FilePath", "DID", "Dt",
        "StartTime", "EndTime", "Machine", "UserName", "ResultCode",
        "Comments", "ServicerID", "SourceProcess", "Job", "DataSource",
        "Priority", "ServerSide", "PID", "Notify", "EmailList",
        "NotificationSent",
    })

    # Case-insensitive lookup → canonical column name
    _COL_LOOKUP = {c.lower(): c for c in _VALID_COLUMNS}

    _ADVANCED_FILTER_ALIASES = {
        "id": "TemplateProcessID",
        "templateprocessid": "TemplateProcessID",
        "processid": "TemplateProcessID",
        "template": "TemplateName",
        "templatename": "TemplateName",
        "scrubber": "TemplateName",
        "did": "DID",
        "deal": "DID",
        "filepath": "FilePath",
        "file": "FilePath",
        "path": "FilePath",
        "servicer": "ServicerID",
        "servicerid": "ServicerID",
        "company": "ServicerID",
        "companyid": "ServicerID",
        "process": "SourceProcess",
        "sourceprocess": "SourceProcess",
        "job": "Job",
        "parser": "Job",
        "datasource": "DataSource",
        "dt": "Dt",
        "date": "Dt",
        "source": "__source__",
        "origin": "__source__",
        "trigger": "__source__",
        "result": "__result__",
        "outcome": "__result__",
        "state": "__result__",
        "status": "__result__",
    }

    _NUMERIC_ADVANCED_FILTERS = frozenset({"TemplateProcessID", "ServicerID"})

    @classmethod
    def _normalise_advanced_filter(cls, filter_name: str) -> Optional[str]:
        if not filter_name:
            return None
        raw = str(filter_name).strip().lower().replace("_", "")
        return cls._ADVANCED_FILTER_ALIASES.get(raw)

    @staticmethod
    def _normalise_result_value(value: str) -> Optional[Dict[str, object]]:
        text = str(value or "").strip().lower()
        if not text:
            return None

        if text in {"success", "succeeded", "ok", "passed", "pass"}:
            return {"sql": "ResultCode = ?", "params": (0,)}
        if text in {"failure", "failed", "error", "errors", "fail"}:
            return {"sql": "ResultCode = ?", "params": (1,)}
        if text in {"queued", "notstarted", "not-started"}:
            return {"sql": "StartTime IS NULL AND EndTime IS NULL", "params": ()}
        if text in {"running", "inprogress", "in-progress", "processing"}:
            return {"sql": "StartTime IS NOT NULL AND EndTime IS NULL", "params": ()}
        if text in {"completed", "done", "finished"}:
            return {"sql": "EndTime IS NOT NULL", "params": ()}
        return None

    @staticmethod
    def _normalise_source_value(value: str) -> Optional[Dict[str, object]]:
        text = str(value or "").strip().lower()
        if not text:
            return None

        if text in {"manual", "manualqueue", "macro"}:
            return {
                "sql": "(SourceProcess = ? OR DataSource LIKE ?)",
                "params": ("ManualQueue", "Queued via macro%"),
            }
        if text in {"sftp", "sftpmonitor"}:
            return {
                "sql": "DataSource LIKE ?",
                "params": ("SFTPMonitor:%",),
            }
        if text in {"email", "mail", "mailbox"}:
            return {
                "sql": "(DataSource IS NOT NULL AND DataSource <> '' AND DataSource NOT LIKE ? AND DataSource NOT LIKE ?)",
                "params": ("SFTPMonitor:%", "Queued via macro%"),
            }
        if text in {"automated", "automation", "activebatch"}:
            return {
                "sql": "(SourceProcess IS NULL OR SourceProcess <> ?)",
                "params": ("ManualQueue",),
            }
        return None

    @classmethod
    def _build_advanced_filter_clause(cls, field_name: str, value: str) -> Optional[Dict[str, object]]:
        canonical = cls._normalise_advanced_filter(field_name)
        if canonical is None:
            return None

        if canonical == "__result__":
            return cls._normalise_result_value(value)

        if canonical == "__source__":
            return cls._normalise_source_value(value)

        if canonical in cls._NUMERIC_ADVANCED_FILTERS:
            try:
                numeric = int(str(value).strip())
            except ValueError:
                return {"sql": "1 = 0", "params": ()}
            return {"sql": f"{canonical} = ?", "params": (numeric,)}

        if canonical == "Dt":
            return {"sql": "Dt = ?", "params": (str(value).strip(),)}

        if canonical == "TemplateProcessID":
            try:
                numeric = int(str(value).strip())
            except ValueError:
                return {"sql": "1 = 0", "params": ()}
            return {"sql": "TemplateProcessID = ?", "params": (numeric,)}

        return {"sql": f"{canonical} LIKE ?", "params": (f"%{str(value).strip()}%",)}

    def filtered_search(
        self,
        filters: Dict[str, str],
        limit: int = 50,
        order_by: str = "StartTime",
    ) -> List[Dict]:
        """Search tblTemplateStaging with an arbitrary set of column filters.

        Parameters
        ----------
        filters:
            ``{column_name: value}`` pairs.  Column names are validated
            against the whitelist; unknown columns are silently dropped.
            Values are bound as parameterised ``= ?`` predicates.
        limit:
            Maximum rows to return (default 50).
        order_by:
            Column to ``ORDER BY … DESC`` (default ``StartTime``).
        """
        clauses: list[str] = []
        params: list = []

        for col_raw, value in filters.items():
            canonical = self._COL_LOOKUP.get(col_raw.lower())
            if canonical is None:
                logger.warning("filtered_search: ignoring unknown column %r", col_raw)
                continue
            clauses.append(f"{canonical} = ?")
            params.append(value)

        if not clauses:
            return []

        # Validate order_by against whitelist
        order_col = self._COL_LOOKUP.get(order_by.lower(), "StartTime")

        where = " AND ".join(clauses)
        sql = (
            "SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,"
            "       StartTime, EndTime, Machine, UserName, ResultCode,"
            "       Comments, ServicerID, SourceProcess, Job, DataSource,"
            "       Priority, ServerSide, PID, Notify, EmailList, NotificationSent"
            f" FROM tblTemplateStaging"
            f" WHERE {where}"
            f" ORDER BY {order_col} DESC"
            f" LIMIT ?"
        )
        params.append(limit)

        cursor = self._exec(sql, tuple(params))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def advanced_search(
        self,
        filters: Optional[List[Dict[str, str]]] = None,
        query: Optional[str] = None,
        days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        order_by: str = "StartTime",
    ) -> List[Dict]:
        """Search tblTemplateStaging with mixed text, semantic, and date filters.

        Supports deterministic staging filters such as template/scrubber,
        DID, ServicerID, FilePath, source type (email/sftp/manual), and
        result state (success/failed/queued/running).
        """
        clauses: list[str] = []
        params: list = []

        for entry in filters or []:
            field_name = str(entry.get("field") or entry.get("type") or "").strip()
            value = str(entry.get("value") or entry.get("query") or "").strip()
            if not field_name or not value:
                continue

            clause = self._build_advanced_filter_clause(field_name, value)
            if clause is None:
                logger.warning("advanced_search: ignoring unknown filter %r", field_name)
                continue

            clauses.append(str(clause["sql"]))
            params.extend(clause.get("params", ()))

        if query:
            clauses.append("(TemplateName LIKE ? OR DID LIKE ? OR FilePath LIKE ? OR Job LIKE ? OR DataSource LIKE ?)")
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])

        if days is not None:
            cutoff = self._cutoff_datetime(int(days))
            clauses.append(f"{_EXECUTION_TS_SQL} >= ?")
            params.append(cutoff)

        if start_date and end_date:
            clauses.append(f"{_EXECUTION_TS_SQL} BETWEEN ? AND ?")
            params.extend([
                self._normalise_range_start(start_date),
                self._normalise_range_end(end_date),
            ])
        elif start_date:
            clauses.append(f"{_EXECUTION_TS_SQL} >= ?")
            params.append(self._normalise_range_start(start_date))
        elif end_date:
            clauses.append(f"{_EXECUTION_TS_SQL} <= ?")
            params.append(self._normalise_range_end(end_date))

        order_col = self._COL_LOOKUP.get(order_by.lower(), "StartTime")
        where = " AND ".join(clauses) if clauses else "1 = 1"

        sql = (
            "SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,"
            "       StartTime, EndTime, Machine, UserName, ResultCode,"
            "       Comments, ServicerID, SourceProcess, Job, DataSource,"
            "       Priority, ServerSide, PID, Notify, EmailList, NotificationSent"
            "  FROM tblTemplateStaging"
            f" WHERE {where}"
            f" ORDER BY {order_col} DESC"
            " LIMIT ?"
        )
        params.append(limit)

        cursor = self._exec(sql, tuple(params))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_distinct_templates(self, days: Optional[int] = None) -> List[Dict]:
        """Return distinct templates seen in staging, optionally scoped to recent days."""
        sql = (
            "SELECT TemplateName, COUNT(*) AS run_count"
            "  FROM tblTemplateStaging"
            " WHERE TemplateName IS NOT NULL AND TemplateName <> ''"
        )
        params: list = []
        if days is not None:
            cutoff = self._cutoff_datetime(int(days))
            sql += f" AND {_EXECUTION_TS_SQL} >= ?"
            params.append(cutoff)

        sql += " GROUP BY TemplateName ORDER BY run_count DESC, TemplateName"
        cursor = self._exec(sql, tuple(params))
        rows = self._rows_to_dicts(cursor)
        cursor.close()
        return rows

    def get_recent_process_level_runs(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """Return recent runs that have no DID populated.

        These are usually process-level or shelf-level jobs.
        """
        cutoff = self._cutoff_datetime(days)
        sql = (
            "SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,"
            "       StartTime, EndTime, ResultCode, Comments, ServicerID,"
            "       SourceProcess, Job, DataSource"
            "  FROM tblTemplateStaging"
            " WHERE (DID IS NULL OR DID = '')"
            f"   AND {_EXECUTION_TS_SQL} >= ?"
            " ORDER BY StartTime DESC"
            " LIMIT ?"
        )
        cursor = self._exec(sql, (cutoff, limit))
        rows = self._rows_to_dicts(cursor)
        cursor.close()
        return rows

    def get_recent_filepath_samples(self, days: int = 30, limit: int = 100) -> List[Dict]:
        """Return recent runs useful for filepath/source auditing."""
        cutoff = self._cutoff_datetime(days)
        sql = (
            "SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,"
            "       StartTime, EndTime, ResultCode, Comments, ServicerID,"
            "       SourceProcess, Job, DataSource"
            "  FROM tblTemplateStaging"
            f" WHERE {_EXECUTION_TS_SQL} >= ?"
            " ORDER BY StartTime DESC"
            " LIMIT ?"
        )
        cursor = self._exec(sql, (cutoff, limit))
        rows = self._rows_to_dicts(cursor)
        cursor.close()
        return rows

    # ------------------------------------------------------------------ #
    # Phase 5 — advanced query methods
    # ------------------------------------------------------------------ #

    def get_recent_by_query(
        self,
        query: str,
        days: int = 30,
        limit: int = 10,
    ) -> Dict:
        """Return recent runs + summary for a template name, DID, or ServicerID.

        The method auto-detects the query type and returns a dict containing
        ``runs`` (list of row dicts) and ``summary`` (aggregate stats).
        """
        cutoff = self._cutoff_datetime(days)

        # Try as ServicerID (integer)
        try:
            sid = int(query)
            cursor = self._exec(queries.GET_RECENT_BY_SERVICER, (sid, cutoff, limit))
            rows = self._rows_to_dicts(cursor)
            if rows:
                cursor.close()
                return self._build_summary(query, rows, days)
        except ValueError:
            pass

        # Try template name pattern
        cursor = self._exec(queries.GET_RECENT_BY_TEMPLATE_NAME, (f"%{query}%", cutoff, limit))
        rows = self._rows_to_dicts(cursor)
        if rows:
            cursor.close()
            return self._build_summary(query, rows, days)

        # Try DID pattern
        cursor = self._exec(queries.GET_RECENT_BY_DID, (f"%{query}%", cutoff, limit))
        rows = self._rows_to_dicts(cursor)
        cursor.close()
        return self._build_summary(query, rows, days)

    def _build_summary(self, scope: str, rows: List[Dict], days: int) -> Dict:
        """Build a summary dict from a list of run rows."""
        total = len(rows)
        successes = sum(1 for r in rows if r.get("ResultCode") == 0)
        failures = sum(1 for r in rows if r.get("ResultCode") == 1)
        rate = round((successes / total * 100), 1) if total else 0.0

        last_success = None
        last_failure = None
        for r in rows:
            st = r.get("StartTime")
            if st and r.get("ResultCode") == 0 and last_success is None:
                last_success = str(st)
            if st and r.get("ResultCode") == 1 and last_failure is None:
                last_failure = str(st)

        return {
            "scope": scope,
            "period_days": days,
            "total_runs": total,
            "successes": successes,
            "failures": failures,
            "success_rate": rate,
            "last_success": last_success,
            "last_failure": last_failure,
            "runs": rows,
        }

    def get_failure_summary(
        self,
        days: int = 30,
        template: Optional[str] = None,
        did: Optional[str] = None,
    ) -> Dict:
        """Return an analysis of failures in the given period.

        Optionally filtered by *template* name or *did* pattern.
        """
        cutoff = self._cutoff_datetime(days)

        # Get individual failures
        if template:
            cursor = self._exec(queries.GET_FAILURES_BY_TEMPLATE_IN_PERIOD, (f"%{template}%", cutoff))
        elif did:
            cursor = self._exec(queries.GET_FAILURES_BY_DID_IN_PERIOD, (f"%{did}%", cutoff))
        else:
            cursor = self._exec(queries.GET_FAILURES_IN_PERIOD, (cutoff,))
        failures = self._rows_to_dicts(cursor)
        cursor.close()

        # Get grouped failures
        cursor = self._exec(queries.GET_FAILURE_GROUPS, (cutoff,))
        groups_raw = self._rows_to_dicts(cursor)
        cursor.close()

        # Build top templates and DIDs
        top_templates = []
        all_dids: Dict[str, int] = {}
        affected_servicers = set()

        for g in groups_raw:
            top_templates.append({
                "template_name": g.get("TemplateName", ""),
                "failure_count": g.get("failure_count", 0),
                "sample_comment": g.get("sample_comment", ""),
            })
            for d in (g.get("affected_dids") or "").split(", "):
                d = d.strip()
                if d:
                    all_dids[d] = all_dids.get(d, 0) + g.get("failure_count", 0)

        top_dids = sorted(
            [{"did": d, "failure_count": c} for d, c in all_dids.items()],
            key=lambda x: x["failure_count"],
            reverse=True,
        )[:20]

        for f in failures:
            sid = f.get("ServicerID")
            if sid is not None:
                affected_servicers.add(sid)

        return {
            "total_failures": len(failures),
            "period_days": days,
            "top_templates": top_templates[:20],
            "top_dids": top_dids,
            "error_groups": [
                {
                    "pattern": g.get("TemplateName", ""),
                    "count": g.get("failure_count", 0),
                    "sample_comment": g.get("sample_comment", ""),
                    "affected_dids": g.get("affected_dids", ""),
                }
                for g in groups_raw[:20]
            ],
            "affected_servicers": sorted(affected_servicers),
            "failures": failures[:50],
        }

    def get_duration_stats(
        self,
        days: int = 30,
        template: Optional[str] = None,
    ) -> Dict:
        """Return processing duration statistics.

        Optionally filtered by *template* name.
        """
        cutoff = self._cutoff_datetime(days)

        if template:
            cursor = self._exec(queries.GET_DURATION_STATS_BY_TEMPLATE, (f"%{template}%", cutoff))
        else:
            cursor = self._exec(queries.GET_DURATION_STATS, (cutoff,))
        stats_raw = self._rows_to_dicts(cursor)
        cursor.close()

        # Get outliers
        cursor = self._exec(queries.GET_DURATION_OUTLIERS, (cutoff, cutoff))
        outliers = self._rows_to_dicts(cursor)
        cursor.close()

        templates = []
        for s in stats_raw:
            templates.append({
                "template_name": s.get("TemplateName", ""),
                "total_runs": s.get("total_runs", 0),
                "avg_seconds": round(float(s.get("avg_seconds") or 0), 2),
                "min_seconds": round(float(s.get("min_seconds") or 0), 2),
                "max_seconds": round(float(s.get("max_seconds") or 0), 2),
            })

        return {
            "period_days": days,
            "templates": templates,
            "outliers": [
                {
                    "template_process_id": o.get("TemplateProcessID"),
                    "template_name": o.get("TemplateName", ""),
                    "file_path": o.get("FilePath", ""),
                    "did": o.get("DID", ""),
                    "duration_secs": round(float(o.get("duration_secs") or 0), 2),
                    "dt": str(o.get("Dt", "")),
                }
                for o in outliers
            ],
        }

    def get_manual_queue_stats(self, days: int = 30) -> Dict:
        """Return manual vs automated processing breakdown."""
        cutoff = self._cutoff_datetime(days)

        # Overall breakdown
        cursor = self._exec(queries.GET_SOURCE_PROCESS_BREAKDOWN, (cutoff,))
        breakdown = self._rows_to_dicts(cursor)
        cursor.close()

        automated = 0
        manual = 0
        for row in breakdown:
            sp = (row.get("SourceProcess") or "").strip()
            count = row.get("run_count", 0)
            if sp == "ManualQueue":
                manual += count
            else:
                automated += count

        total = automated + manual

        # Top manual templates
        cursor = self._exec(queries.GET_MANUAL_QUEUE_BY_TEMPLATE, (cutoff,))
        top_templates = self._rows_to_dicts(cursor)
        cursor.close()

        # Top manual DIDs
        cursor = self._exec(queries.GET_MANUAL_QUEUE_BY_DID, (cutoff,))
        top_dids = self._rows_to_dicts(cursor)
        cursor.close()

        # Operators
        cursor = self._exec(queries.GET_MANUAL_QUEUE_OPERATORS, (cutoff,))
        operators_raw = self._rows_to_dicts(cursor)
        cursor.close()

        # Parse operator names from DataSource ("Queued via macro by USERNAME")
        operators = []
        for op in operators_raw:
            ds = op.get("DataSource", "")
            name = ds
            if "by " in ds:
                name = ds.split("by ", 1)[1].strip()
            operators.append({
                "operator": name,
                "queue_count": op.get("queue_count", 0),
            })

        return {
            "automated_count": automated,
            "manual_count": manual,
            "total_count": total,
            "manual_percentage": round((manual / total * 100), 1) if total else 0.0,
            "top_manual_templates": [
                {"template_name": t.get("TemplateName", ""), "manual_count": t.get("manual_count", 0)}
                for t in top_templates[:20]
            ],
            "top_manual_dids": [
                {"did": d.get("DID", ""), "manual_count": d.get("manual_count", 0)}
                for d in top_dids[:20]
            ],
            "manual_operators": operators[:20],
            "period_days": days,
        }

    def trace_by_filepath(self, filepath_pattern: str, limit: int = 10) -> List[Dict]:
        """Trace files matching *filepath_pattern* with their DataSource origin.

        Returns enriched dicts with a ``source_type`` field parsed from DataSource.
        """
        cursor = self._exec(queries.TRACE_BY_FILEPATH, (f"%{filepath_pattern}%", limit))
        rows = self._rows_to_dicts(cursor)
        cursor.close()

        for row in rows:
            ds = (row.get("DataSource") or "").strip()
            if "SFTPMonitor:" in ds:
                row["source_type"] = "sftp"
            elif "Queued via macro" in ds or row.get("SourceProcess") == "ManualQueue":
                row["source_type"] = "manual"
            elif ds:
                row["source_type"] = "email"
            else:
                row["source_type"] = "unknown"

            # Calculate duration
            st = row.get("StartTime")
            et = row.get("EndTime")
            if st and et:
                try:
                    from datetime import datetime as _dt
                    if not isinstance(st, _dt):
                        st = _dt.fromisoformat(str(st))
                    if not isinstance(et, _dt):
                        et = _dt.fromisoformat(str(et))
                    row["duration_seconds"] = round((et - st).total_seconds(), 2)
                except (ValueError, TypeError):
                    row["duration_seconds"] = None
            else:
                row["duration_seconds"] = None

        return rows

    def get_processing_for_servicer(self, servicer_id: int, limit: int = 50) -> Dict:
        """Return processing runs + summary for a given ServicerID."""
        cursor = self._exec(queries.GET_PROCESSING_FOR_SERVICER, (servicer_id, limit))
        runs = self._rows_to_dicts(cursor)
        cursor.close()

        cursor = self._exec(queries.GET_SUMMARY_FOR_SERVICER, (servicer_id,))
        row = cursor.fetchone()
        cursor.close()

        summary = {}
        if row:
            cols = ["total_runs", "successes", "failures", "unique_templates",
                    "unique_deals", "last_success", "last_failure"]
            summary = {cols[i]: row[i] for i in range(len(cols))}
            total = summary.get("total_runs", 0) or 0
            successes = summary.get("successes", 0) or 0
            summary["success_rate"] = round((successes / total * 100), 1) if total else 0.0
            # Convert timestamps to strings
            for k in ("last_success", "last_failure"):
                if summary.get(k):
                    summary[k] = str(summary[k])

        return {
            "servicer_id": servicer_id,
            "summary": summary,
            "runs": runs,
        }

    def get_pipeline_status(self, servicer_id: int, days: int = 30) -> Dict:
        """Return pipeline status for a servicer: mapping + execution layers.

        The config layer (Settings.xml) must be assembled by the caller.
        """
        cutoff = self._cutoff_datetime(days)

        # Execution layer
        cursor = self._exec(queries.GET_RECENT_BY_SERVICER, (servicer_id, cutoff, 100))
        runs = self._rows_to_dicts(cursor)
        cursor.close()

        total = len(runs)
        successes = sum(1 for r in runs if r.get("ResultCode") == 0)
        failures = total - successes
        health_score = round((successes / total * 100), 1) if total else 0.0

        unique_templates = list({r.get("TemplateName") for r in runs if r.get("TemplateName")})
        unique_dids = list({r.get("DID") for r in runs if r.get("DID")})

        return {
            "servicer_id": servicer_id,
            "period_days": days,
            "execution_layer": {
                "status": "ok" if health_score >= 90 else ("warning" if health_score >= 50 else "critical"),
                "total_runs": total,
                "successes": successes,
                "failures": failures,
                "health_score": health_score,
                "unique_templates": unique_templates,
                "unique_dids": unique_dids,
                "recent_runs": runs[:10],
            },
        }

    # ------------------------------------------------------------------ #
    # Cleanup / context manager
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
                logger.info("TemplateStagingRepository connection closed.")
            except Exception:
                logger.debug("Connection already closed or unavailable.")
            finally:
                self._conn = None

    def __enter__(self) -> "TemplateStagingRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
