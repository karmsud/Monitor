"""Phase 4 — Advanced Analysis Layer.

Public API:
    TrendAnalyzer          – L-06 timeline trend analysis
    PerformanceBenchmarker – L-07 job performance benchmarking
    ConsolidationAnalyzer  – A-01 job consolidation candidates
    ImpactSimulator        – A-02 change impact simulation
    HealthChecker          – A-03 full system health check
"""

from backend.analysis.models import (
    TrendDay,
    TrendSummary,
    PerformanceEntry,
    PerformanceSummary,
    ConsolidationCandidate,
    ConsolidationGroup,
    ConsolidationReport,
    ChangeSpec,
    AffectedEntity,
    ImpactReport,
    HealthSection,
    HealthReport,
)
from backend.analysis.trends import TrendAnalyzer
from backend.analysis.performance import PerformanceBenchmarker
from backend.analysis.consolidation import ConsolidationAnalyzer
from backend.analysis.impact import ImpactSimulator
from backend.analysis.health import HealthChecker

__all__ = [
    "TrendDay",
    "TrendSummary",
    "PerformanceEntry",
    "PerformanceSummary",
    "ConsolidationCandidate",
    "ConsolidationGroup",
    "ConsolidationReport",
    "ChangeSpec",
    "AffectedEntity",
    "ImpactReport",
    "HealthSection",
    "HealthReport",
    "TrendAnalyzer",
    "PerformanceBenchmarker",
    "ConsolidationAnalyzer",
    "ImpactSimulator",
    "HealthChecker",
]
