"""FRP Agent error codes."""

# Phase 1
XML_001 = "XML_001"  # Settings.xml parse error
XML_002 = "XML_002"  # Missing Outlook element
DB_001 = "DB_001"    # Database connection failed

# Phase 3 additions
LOG_001 = "LOG_001"  # Log database not found
LOG_002 = "LOG_002"  # Log database missing tables
LOG_003 = "LOG_003"  # No jobs match name
LOG_004 = "LOG_004"  # Ambiguous job name
MSG_001 = "MSG_001"  # .msg file not found
MSG_002 = "MSG_002"  # Unsupported file type
MSG_003 = "MSG_003"  # Failed to parse .msg
TRIAGE_001 = "TRIAGE_001"  # Settings.xml parse failed
