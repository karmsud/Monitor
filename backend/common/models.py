"""Common response models shared across the FRP Agent backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CliResponse:
    """Standardised response envelope returned by every CLI command."""

    success: bool
    command: str
    data: Optional[Any] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    # -- helpers ---------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for JSON serialisation."""
        return asdict(self)

    def add_error(self, message: str) -> None:
        """Append an error and mark the response as failed."""
        self.errors.append(message)
        self.success = False

    def add_warning(self, message: str) -> None:
        """Append a non-fatal warning."""
        self.warnings.append(message)
