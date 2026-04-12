"""Central configuration for the FRP Agent backend.

Values are read from environment variables with sensible defaults so the
agent works out-of-the-box in development and can be overridden per
environment in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FrpConfig:
    """Immutable configuration bag populated from environment variables."""

    prod_mode: bool = False
    outlook_settings_path: str = ""
    sftp_settings_path: str = ""
    email_log_folder: str = ""
    sftp_log_folder: str = ""
    log_retention_months: int = 6
    log_level: str = "INFO"
    secrets_path: str = ""
    log_db_path: str = "frp_logs.db"

    # -- factory ---------------------------------------------------------- #

    @classmethod
    def from_env(cls) -> "FrpConfig":
        """Build a *FrpConfig* from the current environment variables.

        Environment variable names follow the convention ``FRP_<FIELD>``.
        Boolean values accept ``1 / true / yes`` (case-insensitive).
        """

        def _bool(val: str) -> bool:
            return val.strip().lower() in ("1", "true", "yes")

        return cls(
            prod_mode=_bool(os.getenv("FRP_PROD_MODE", "false")),
            outlook_settings_path=os.getenv("FRP_OUTLOOK_SETTINGS_PATH", ""),
            sftp_settings_path=os.getenv("FRP_SFTP_SETTINGS_PATH", ""),
            email_log_folder=os.getenv("FRP_EMAIL_LOG_FOLDER", ""),
            sftp_log_folder=os.getenv("FRP_SFTP_LOG_FOLDER", ""),
            log_retention_months=int(os.getenv("FRP_LOG_RETENTION_MONTHS", "6")),
            log_level=os.getenv("FRP_LOG_LEVEL", "INFO"),
            secrets_path=os.getenv("FRP_SECRETS_PATH", ""),
            log_db_path=os.getenv("FRP_LOG_DB_PATH", "frp_logs.db"),
        )
