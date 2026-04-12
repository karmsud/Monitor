"""SQL query constants used by the database access layer.

All queries use ``?`` parameter placeholders (DB-API 2.0 / pyodbc style).
"""

# -- Servicer ---------------------------------------------------------------- #

CHECK_SERVICER_EXISTS: str = """
SELECT COUNT(*) AS cnt
  FROM tblCompany
 WHERE CompanyID = ?
"""

GET_ALL_SERVICER_IDS: str = """
SELECT CompanyID,
       CompanyName
  FROM tblCompany
 ORDER BY CompanyID
"""

# -- Deals ------------------------------------------------------------------- #

GET_DEALS_BY_COMPANY: str = """
SELECT d.DealID,
       d.DealName,
       d.CompanyID,
       c.CompanyName
  FROM tblDeal   d
  JOIN tblCompany c ON c.CompanyID = d.CompanyID
 WHERE d.CompanyID = ?
 ORDER BY d.DealID
"""

GET_DEALS_BY_DID: str = """
SELECT d.DealID,
       d.DealName,
       d.CompanyID,
       c.CompanyName
  FROM tblDeal   d
  JOIN tblCompany c ON c.CompanyID = d.CompanyID
 WHERE d.DealID = ?
"""

# -- Company summary --------------------------------------------------------- #

GET_COMPANY_SUMMARY: str = """
SELECT c.CompanyID,
       c.CompanyName,
       COUNT(d.DealID) AS DealCount
  FROM tblCompany c
  LEFT JOIN tblDeal d ON d.CompanyID = c.CompanyID
 WHERE c.CompanyID = ?
 GROUP BY c.CompanyID, c.CompanyName
"""

# -- External DID / Import DID ---------------------------------------------- #

SEARCH_BY_IMPORT_DID: str = """
SELECT ExternalDIDRefID,
       DealID,
       ExternalDID,
       ImportDID
  FROM tblExternalDIDRef
 WHERE ImportDID LIKE ?
 ORDER BY DealID
"""

# -- tblExternalDIDRef (DealRepository) -------------------------------------- #

GET_ALL_DIDREF: str = """
SELECT ItemID,
       DID,
       ImportDID,
       CompanyID
  FROM tblExternalDIDRef
 ORDER BY DID
"""

GET_DIDREF_SUMMARY: str = """
SELECT COUNT(*)                  AS total_rows,
       COUNT(DISTINCT DID)       AS unique_dids,
       COUNT(DISTINCT ImportDID) AS unique_keywords,
       COUNT(DISTINCT CompanyID) AS unique_companies
  FROM tblExternalDIDRef
"""

CHECK_COMPANY_EXISTS_DIDREF: str = """
SELECT COUNT(*) AS cnt
  FROM tblExternalDIDRef
 WHERE CompanyID = ?
"""

GET_DIDREF_BY_COMPANY: str = """
SELECT DID,
       ImportDID,
       CompanyID
  FROM tblExternalDIDRef
 WHERE CompanyID = ?
 ORDER BY DID
"""

GET_DIDREF_COMPANY_SUMMARY: str = """
SELECT COUNT(*)                AS total_rows,
       COUNT(DISTINCT DID)     AS unique_deals,
       COUNT(DISTINCT ImportDID) AS unique_keywords
  FROM tblExternalDIDRef
 WHERE CompanyID = ?
"""

GET_ALL_DIDREF_COMPANY_IDS: str = """
SELECT DISTINCT CompanyID
  FROM tblExternalDIDRef
 ORDER BY CompanyID
"""

SEARCH_BY_DID: str = """
SELECT ItemID,
       DID,
       ImportDID,
       CompanyID
  FROM tblExternalDIDRef
 WHERE DID LIKE ?
 ORDER BY DID
"""

SEARCH_BY_IMPORT_DID_DIDREF: str = """
SELECT ItemID,
       DID,
       ImportDID,
       CompanyID
  FROM tblExternalDIDRef
 WHERE ImportDID LIKE ?
 ORDER BY DID
"""

# -- Phase 2: Coverage Intelligence ------------------------------------------ #

GET_COMPANIES_BY_IMPORT_DID: str = """
SELECT DISTINCT CompanyID
  FROM tblExternalDIDRef
 WHERE UPPER(ImportDID) = UPPER(?)
"""

GET_ALL_DISTINCT_COMPANY_IDS: str = """
SELECT DISTINCT CompanyID
  FROM tblExternalDIDRef
 ORDER BY CompanyID
"""

GET_DEAL_COUNT_BY_COMPANY: str = """
SELECT CompanyID,
       COUNT(*) AS deal_count
  FROM tblExternalDIDRef
 WHERE CompanyID = ?
 GROUP BY CompanyID
"""

SEARCH_IMPORT_DID_MATCHES: str = """
SELECT DISTINCT CompanyID,
       ImportDID,
       COUNT(*) AS match_count
  FROM tblExternalDIDRef
 WHERE UPPER(ImportDID) = UPPER(?)
 GROUP BY CompanyID, ImportDID
"""

# -- tblTemplateStaging ------------------------------------------------------ #
# Note: In US Bank prod, query via "ToolsHub.ToolsHub.dbo.tblTemplateStaging"
# In local MySQL dev, query via "tblTemplateStaging" directly.

TEMPLATE_STAGING_EXECUTION_TS: str = "COALESCE(StartTime, EndTime, Dt)"

GET_TEMPLATE_STAGING_BY_ID: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE TemplateProcessID = ?
"""

GET_TEMPLATE_STAGING_BY_TEMPLATE_NAME: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE TemplateName = ?
 ORDER BY StartTime DESC
"""

GET_TEMPLATE_STAGING_BY_DID: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE DID = ?
 ORDER BY StartTime DESC
"""

SEARCH_TEMPLATE_STAGING_BY_DID: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE DID LIKE ?
 ORDER BY StartTime DESC
"""

GET_TEMPLATE_STAGING_FAILURES: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments
  FROM tblTemplateStaging
 WHERE ResultCode = 1
 ORDER BY StartTime DESC
"""

GET_TEMPLATE_STAGING_SUCCESSES: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments
  FROM tblTemplateStaging
 WHERE ResultCode = 0
 ORDER BY StartTime DESC
"""

GET_TEMPLATE_STAGING_BY_DATE_RANGE: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE """ + TEMPLATE_STAGING_EXECUTION_TS + """ BETWEEN ? AND ?
 ORDER BY StartTime DESC
"""

GET_TEMPLATE_STAGING_BY_QUERY_AND_DATE_RANGE: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE (DID LIKE ? OR TemplateName LIKE ?)
   AND StartTime BETWEEN ? AND ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_TEMPLATE_STAGING_SUMMARY: str = """
SELECT COUNT(*)                          AS total_runs,
       SUM(CASE WHEN ResultCode = 0 THEN 1 ELSE 0 END) AS successes,
       SUM(CASE WHEN ResultCode = 1 THEN 1 ELSE 0 END) AS failures,
       COUNT(DISTINCT TemplateName)      AS unique_templates,
       COUNT(DISTINCT DID)               AS unique_deals
  FROM tblTemplateStaging
"""

GET_TEMPLATE_STAGING_SUMMARY_BY_TEMPLATE: str = """
SELECT TemplateName,
       COUNT(*)                          AS total_runs,
       SUM(CASE WHEN ResultCode = 0 THEN 1 ELSE 0 END) AS successes,
       SUM(CASE WHEN ResultCode = 1 THEN 1 ELSE 0 END) AS failures
  FROM tblTemplateStaging
 WHERE TemplateName = ?
 GROUP BY TemplateName
"""

SEARCH_TEMPLATE_STAGING_BY_FILEPATH: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, ResultCode, Comments
  FROM tblTemplateStaging
 WHERE FilePath LIKE ?
 ORDER BY StartTime DESC
"""

GET_ALL_TEMPLATE_NAMES: str = """
SELECT DISTINCT TemplateName
  FROM tblTemplateStaging
 ORDER BY TemplateName
"""

# -- Phase 5: tblTemplateStaging — advanced queries ----------------------- #

GET_RECENT_BY_TEMPLATE_NAME: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE TemplateName LIKE ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_RECENT_BY_DID: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE DID LIKE ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_RECENT_BY_SERVICER: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource,
       Priority, ServerSide, PID, Notify, EmailList, NotificationSent
  FROM tblTemplateStaging
 WHERE ServicerID = ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_FAILURES_IN_PERIOD: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, ResultCode, Comments,
       ServicerID, SourceProcess, Job, DataSource
  FROM tblTemplateStaging
 WHERE ResultCode = 1
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
"""

GET_FAILURES_BY_TEMPLATE_IN_PERIOD: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, ResultCode, Comments,
       ServicerID, SourceProcess, Job, DataSource
  FROM tblTemplateStaging
 WHERE ResultCode = 1
   AND TemplateName LIKE ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
"""

GET_FAILURES_BY_DID_IN_PERIOD: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, ResultCode, Comments,
       ServicerID, SourceProcess, Job, DataSource
  FROM tblTemplateStaging
 WHERE ResultCode = 1
   AND DID LIKE ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 ORDER BY StartTime DESC
"""

GET_FAILURE_GROUPS: str = """
SELECT TemplateName,
       COUNT(*)                AS failure_count,
       GROUP_CONCAT(DISTINCT DID ORDER BY DID SEPARATOR ', ')  AS affected_dids,
       MAX(Comments)           AS sample_comment
  FROM tblTemplateStaging
 WHERE ResultCode = 1
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY TemplateName
 ORDER BY failure_count DESC
"""

GET_DURATION_STATS: str = """
SELECT TemplateName,
       COUNT(*)                                       AS total_runs,
       AVG(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS avg_seconds,
       MIN(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS min_seconds,
       MAX(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS max_seconds
  FROM tblTemplateStaging
 WHERE StartTime IS NOT NULL
   AND EndTime IS NOT NULL
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY TemplateName
 ORDER BY avg_seconds DESC
"""

GET_DURATION_STATS_BY_TEMPLATE: str = """
SELECT TemplateName,
       COUNT(*)                                       AS total_runs,
       AVG(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS avg_seconds,
       MIN(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS min_seconds,
       MAX(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) AS max_seconds
  FROM tblTemplateStaging
 WHERE StartTime IS NOT NULL
   AND EndTime IS NOT NULL
   AND TemplateName LIKE ?
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY TemplateName
 ORDER BY avg_seconds DESC
"""

GET_DURATION_OUTLIERS: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime,
       TIMESTAMPDIFF(SECOND, StartTime, EndTime) AS duration_secs
  FROM tblTemplateStaging
 WHERE StartTime IS NOT NULL
   AND EndTime IS NOT NULL
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
   AND TIMESTAMPDIFF(SECOND, StartTime, EndTime) > (
       SELECT AVG(TIMESTAMPDIFF(SECOND, StartTime, EndTime)) * 2
         FROM tblTemplateStaging
        WHERE StartTime IS NOT NULL
          AND EndTime IS NOT NULL
          AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
   )
 ORDER BY duration_secs DESC
 LIMIT 20
"""

GET_SOURCE_PROCESS_BREAKDOWN: str = """
SELECT SourceProcess,
       COUNT(*) AS run_count
  FROM tblTemplateStaging
 WHERE """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY SourceProcess
"""

GET_MANUAL_QUEUE_BY_TEMPLATE: str = """
SELECT TemplateName,
       COUNT(*) AS manual_count
  FROM tblTemplateStaging
 WHERE SourceProcess = 'ManualQueue'
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY TemplateName
 ORDER BY manual_count DESC
"""

GET_MANUAL_QUEUE_BY_DID: str = """
SELECT DID,
       COUNT(*) AS manual_count
  FROM tblTemplateStaging
 WHERE SourceProcess = 'ManualQueue'
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY DID
 ORDER BY manual_count DESC
"""

GET_MANUAL_QUEUE_OPERATORS: str = """
SELECT DataSource,
       COUNT(*) AS queue_count
  FROM tblTemplateStaging
 WHERE SourceProcess = 'ManualQueue'
   AND """ + TEMPLATE_STAGING_EXECUTION_TS + """ >= ?
 GROUP BY DataSource
 ORDER BY queue_count DESC
"""

TRACE_BY_FILEPATH: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource
  FROM tblTemplateStaging
 WHERE FilePath LIKE ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_PROCESSING_FOR_SERVICER: str = """
SELECT TemplateProcessID, TemplateName, FilePath, DID, Dt,
       StartTime, EndTime, Machine, UserName, ResultCode,
       Comments, ServicerID, SourceProcess, Job, DataSource
  FROM tblTemplateStaging
 WHERE ServicerID = ?
 ORDER BY StartTime DESC
 LIMIT ?
"""

GET_SUMMARY_FOR_SERVICER: str = """
SELECT COUNT(*)                          AS total_runs,
       SUM(CASE WHEN ResultCode = 0 THEN 1 ELSE 0 END) AS successes,
       SUM(CASE WHEN ResultCode = 1 THEN 1 ELSE 0 END) AS failures,
       COUNT(DISTINCT TemplateName)      AS unique_templates,
       COUNT(DISTINCT DID)               AS unique_deals,
       MAX(CASE WHEN ResultCode = 0 THEN StartTime END) AS last_success,
       MAX(CASE WHEN ResultCode = 1 THEN StartTime END) AS last_failure
  FROM tblTemplateStaging
 WHERE ServicerID = ?
"""

