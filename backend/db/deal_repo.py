"""Data-access layer for the tblExternalDIDRef table.

Provides read-only helpers used by the CLI and agent layers to query
servicer / deal / DID information.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from backend.db.connection import get_connection
from backend.db import queries

logger = logging.getLogger("frp.db.deal_repo")


class DealRepository:
    """Repository wrapping parameterised queries against tblExternalDIDRef."""

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
            Optional override for the JSON secrets file.  When *None* the
            default path resolved by :func:`get_connection` is used.
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
            "DealRepository initialised (prod_mode=%s)", prod_mode,
        )

    # ------------------------------------------------------------------ #
    # Helper: row → dict
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rows_to_dicts(cursor) -> List[Dict]:
        """Convert all rows under *cursor* to a list of column-keyed dicts."""
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    # Public query methods
    # ------------------------------------------------------------------ #

    def get_all_deals(self, limit: int = 500) -> List[Dict]:
        """Return all rows from tblExternalDIDRef (capped at *limit*)."""
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_ALL_DIDREF)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchmany(limit)]
        cursor.close()
        return results

    def get_table_summary(self) -> Dict:
        """Return aggregate counts for tblExternalDIDRef."""
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_DIDREF_SUMMARY)
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return {"total_rows": 0, "unique_dids": 0, "unique_keywords": 0, "unique_companies": 0}
        return {
            "total_rows": row[0],
            "unique_dids": row[1],
            "unique_keywords": row[2],
            "unique_companies": row[3],
        }

    def servicer_exists(self, company_id: int) -> bool:
        """Return ``True`` when *company_id* has at least one row in tblExternalDIDRef."""
        cursor = self._conn.cursor()
        cursor.execute(queries.CHECK_COMPANY_EXISTS_DIDREF, (company_id,))
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        return count > 0

    def get_deals_by_company(self, company_id: int) -> List[Dict]:
        """Return every DID mapping row for *company_id*.

        Each dict contains keys ``DID``, ``ImportDID``, ``CompanyID``.
        """
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_DIDREF_BY_COMPANY, (company_id,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def get_company_summary(self, company_id: int) -> Dict:
        """Return aggregate stats for *company_id*.

        Returns a dict with ``total_rows``, ``unique_deals``,
        ``unique_keywords``, and the queried ``company_id``.
        """
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_DIDREF_COMPANY_SUMMARY, (company_id,))
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            return {
                "company_id": company_id,
                "total_rows": 0,
                "unique_deals": 0,
                "unique_keywords": 0,
            }

        return {
            "company_id": company_id,
            "total_rows": row[0],
            "unique_deals": row[1],
            "unique_keywords": row[2],
        }

    def get_all_servicer_ids(self) -> Set[int]:
        """Return every distinct ``CompanyID`` present in tblExternalDIDRef."""
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_ALL_DIDREF_COMPANY_IDS)
        ids: Set[int] = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return ids

    def search_by_did(self, did_pattern: str) -> List[Dict]:
        """Search tblExternalDIDRef where ``DID LIKE ?``.

        *did_pattern* should include SQL wildcards, e.g. ``%ABSC%``.
        """
        cursor = self._conn.cursor()
        cursor.execute(queries.SEARCH_BY_DID, (did_pattern,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def search_by_import_did(self, keyword: str) -> List[Dict]:
        """Search tblExternalDIDRef where ``ImportDID LIKE ?``.

        *keyword* should include SQL wildcards, e.g. ``%M70%``.
        """
        cursor = self._conn.cursor()
        cursor.execute(queries.SEARCH_BY_IMPORT_DID_DIDREF, (keyword,))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    def search_deals_by_filters(self, filters: List[Dict[str, str]]) -> List[Dict]:
        """Search tblExternalDIDRef using combined deterministic AND filters."""
        if not filters:
            return []

        clauses = []
        params = []
        seen = set()

        for entry in filters:
          lookup_type = str(entry.get("type") or "").strip().lower()
          value = str(entry.get("value") or "").strip()
          canonical = "company" if lookup_type in ("company", "servicer") else lookup_type

          if canonical in seen:
              raise ValueError(f"Duplicate deal filter type: {lookup_type}")
          seen.add(canonical)

          if lookup_type == "did":
              clauses.append("DID LIKE ?")
              params.append(f"%{value}%")
          elif lookup_type == "keyword":
              clauses.append("ImportDID LIKE ?")
              params.append(f"%{value}%")
          elif lookup_type in ("company", "servicer"):
              company_id = self._extract_numeric_id(value)
              if company_id is None:
                  return []
              clauses.append("CompanyID = ?")
              params.append(company_id)
          else:
              raise ValueError(f"Unsupported deal filter type: {lookup_type}")

        sql = """
SELECT ItemID,
       DID,
       ImportDID,
       CompanyID
  FROM tblExternalDIDRef
 WHERE """ + "\n   AND ".join(clauses) + "\n ORDER BY DID"

        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params))
        results = self._rows_to_dicts(cursor)
        cursor.close()
        return results

    # ------------------------------------------------------------------ #
    #  Phase 2: Coverage Intelligence queries
    # ------------------------------------------------------------------ #

    def get_companies_by_import_did(self, import_did: str) -> list:
        """Get all distinct CompanyIDs that have deals matching an ImportDID value."""
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_COMPANIES_BY_IMPORT_DID, (import_did,))
        results = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return results

    def get_all_distinct_company_ids(self) -> list:
        """Get all distinct CompanyIDs in the database."""
        cursor = self._conn.cursor()
        cursor.execute(queries.GET_ALL_DISTINCT_COMPANY_IDS)
        results = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return results

    # ------------------------------------------------------------------ #
    #  Phase 3: Triage support queries
    # ------------------------------------------------------------------ #

    def resolve_did_by_name(self, did_identifier: str) -> Optional[str]:
        """Resolve a DID name or number to its ImportDID keyword.

        Tries in order: numeric DID lookup, exact ImportDID match, then
        partial LIKE match (returns ``None`` if zero or 2+ partials).
        """
        cursor = self._conn.cursor()
        # Try as number first
        try:
            did_num = int(did_identifier)
            cursor.execute(
                "SELECT ImportDID FROM tblExternalDIDRef WHERE DID = ?",
                (did_num,),
            )
            row = cursor.fetchone()
            if row:
                cursor.close()
                return row[0]
        except ValueError:
            pass
        # Try exact match
        cursor.execute(
            "SELECT DISTINCT ImportDID FROM tblExternalDIDRef WHERE ImportDID = ?",
            (did_identifier,),
        )
        row = cursor.fetchone()
        if row:
            cursor.close()
            return row[0]
        # Try partial
        cursor.execute(
            "SELECT DISTINCT ImportDID FROM tblExternalDIDRef WHERE ImportDID LIKE ?",
            (f"%{did_identifier}%",),
        )
        rows = cursor.fetchall()
        cursor.close()
        if len(rows) == 1:
            return rows[0][0]
        return None

    def get_companies_by_sender_domain(self, domain: str) -> List:
        """Find companies whose ImportDID contains the domain prefix.

        Uses a heuristic: extract the first segment of the domain
        (e.g. ``acme`` from ``acme.com``) and search ImportDID.
        """
        prefix = domain.split(".")[0].upper() if "." in domain else domain.upper()
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT DISTINCT CompanyID FROM tblExternalDIDRef WHERE ImportDID LIKE ?",
            (f"%{prefix}%",),
        )
        results = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return results

    # ------------------------------------------------------------------ #
    # Convenience wrappers used by CLI commands
    # ------------------------------------------------------------------ #

    def get_deals_for_servicer(self, servicer_id: int) -> List[Dict]:
        """Return all DID rows for a servicer (alias for get_deals_by_company)."""
        return self.get_deals_by_company(servicer_id)

    @staticmethod
    def _extract_numeric_id(text: str) -> Optional[int]:
        """Extract a numeric ID from strings like '296', 'CompanyID 296', 'servicer 569'."""
        import re
        # Direct integer
        try:
            return int(text)
        except ValueError:
            pass
        # Extract trailing number from label patterns
        m = re.search(r'\b(\d{1,10})\b', text)
        if m:
            return int(m.group(1))
        return None

    def search_deals(self, query: str) -> List[Dict]:
        """Search tblExternalDIDRef by DID name, ImportDID keyword, or CompanyID number.

        Handles queries like '296', 'CompanyID 296', 'servicer 569',
        'CMLTI 2014-A', etc.
        """
        # Try as CompanyID number (handles "296" and "CompanyID 296")
        cid = self._extract_numeric_id(query)
        if cid is not None:
            results = self.get_deals_by_company(cid)
            if results:
                return results
        # Try DID name
        results = self.search_by_did(f"%{query}%")
        if results:
            return results
        # Try ImportDID keyword
        return self.search_by_import_did(f"%{query}%")

    # ------------------------------------------------------------------ #
    # Cleanup / context manager
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
                logger.info("DealRepository connection closed.")
            except Exception:
                logger.debug("Connection already closed or unavailable.")
            finally:
                self._conn = None

    def __enter__(self) -> "DealRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
