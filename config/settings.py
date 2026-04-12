"""Re-export FrpConfig so it is importable from the config package.

Usage::

    from config.settings import FrpConfig

    cfg = FrpConfig.from_env()
"""

from backend.common.config import FrpConfig  # noqa: F401

__all__ = ["FrpConfig"]
