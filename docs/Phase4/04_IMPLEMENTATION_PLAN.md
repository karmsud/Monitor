# Phase 4: Implementation Plan
## FRP Agent — Advanced Analysis Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Total Sprints:** 6 (Sprints 21–26)  
**Estimated Hours:** 28–38 hours  

---

## Table of Contents
1. [Implementation Principles](#1-implementation-principles)
2. [Phase 3 Gate](#2-phase-3-gate)
3. [Sprint Plan](#3-sprint-plan)
4. [Verification Checkpoints](#4-verification-checkpoints)
5. [Rollback Strategy](#5-rollback-strategy)
6. [Minimum Viable Phase 4](#6-minimum-viable-phase-4)

---

## 1. Implementation Principles

1. **Models first, analyzers second, orchestrator last** — Data models are pure and dependency-free. Each analyzer class is independently testable. HealthChecker (the orchestrator) comes last since it depends on everything.
2. **Dependency injection everywhere** — Every Phase 4 class receives its dependencies via constructor. Never instantiate Phase 1–3 classes inside Phase 4 modules.
3. **Batch SQL over iteration** — TrendAnalyzer and PerformanceBenchmarker use single batch SQL queries grouped by job/date, NOT per-job loops. This keeps performance O(1 query) regardless of job count.
4. **Graceful degradation by default** — HealthChecker and ImpactSimulator must handle missing dependencies (DB down, SQLite empty, parser unavailable) without crashing. Every section produces a result, even if it's "unavailable."
5. **LLM for intent parsing only** — The `/analyze impact` command uses LLM to convert natural language into a structured `ChangeSpec`. All actual analysis is deterministic Python — never let the LLM compute coverage or risk.
6. **Test with realistic data** — Use fixtures with ≥10 jobs, ≥100 log events, and ≥50 DID mappings to exercise batch queries and edge cases.

---

## 2. Phase 3 Gate

Before starting Phase 4:

| Prerequisite | Verification |
|-------------|--------------|
| Phase 3 CP-FINAL-P3 passed | All 7 Phase 3 UCs work in Extension Dev Host |
| LogAnalytics proven | `check_staleness()`, `did_failures()`, `job_health()`, `daily_summary()` all tested |
| SQLite index has sufficient data | `frp_logs.db` exists with ≥200 events across ≥5 days |
| Intel modules from Phase 2 | CoverageAnalyzer, OrphanDetector, CollisionDetector tested |
| `_get_conn()` is accessible | LogAnalytics exposes `_get_conn()` for TrendAnalyzer/Benchmarker |
| DealRepository complete | `get_deals_by_company()`, `get_by_import_did()`, `get_by_did()` work |

---

## 3. Sprint Plan

### Sprint 21: Analysis Data Models (2–3h)

**Goal:** Create all Phase 4 data models. Pure dataclasses, no dependencies.

| Task | File | Est. |
|------|------|------|
| Create `backend/analysis/__init__.py` | Package init, export all public classes | 10 min |
| Create `backend/analysis/models.py` | TrendDay, TrendSummary | 20 min |
| Add PerformanceEntry, PerformanceSummary | models.py continuation | 20 min |
| Add ConsolidationCandidate, ConsolidationGroup, ConsolidationReport | models.py continuation | 20 min |
| Add ChangeSpec, AffectedEntity, ImpactReport | models.py continuation | 20 min |
| Add HealthSection, HealthReport | models.py continuation | 15 min |
| Write tests: `test_analysis_models.py` | 25 tests (serialization, from_dict, edge cases) | 45 min |

**Verification: CP-21**
```
pytest tests/analysis/test_analysis_models.py -v     # 25 pass
python -c "from backend.analysis.models import *"    # All models importable
```

---

### Sprint 22: TrendAnalyzer + PerformanceBenchmarker (5–7h)

**Goal:** Build L-06 and L-07 — the two SQLite-heavy analytical engines.

| Task | File | Est. |
|------|------|------|
| Create `backend/analysis/trends.py` | TrendAnalyzer class skeleton | 15 min |
| Implement `_query_period()` | Batch SQL with GROUP BY date | 30 min |
| Implement `_build_day_list()` | Fill gaps with zero-days | 20 min |
| Implement `_add_trend_indicators()` | ↑/↓/→ comparison | 15 min |
| Implement `analyze()` | Full pipeline: query → build → trend → compare → summary | 30 min |
| Create `backend/analysis/performance.py` | PerformanceBenchmarker skeleton | 15 min |
| Implement `_batch_query_metrics()` | Single SQL with per-job aggregation | 30 min |
| Implement `_get_all_job_names()` | Union of parser + SQLite sources | 20 min |
| Implement `benchmark()` | Full pipeline: query → rank → status → summary | 30 min |
| Create conftest fixtures | `analysis_db` with 10 jobs, 14+ days of data | 30 min |
| Write tests: `test_trends.py` | 18 tests | 60 min |
| Write tests: `test_performance.py` | 18 tests | 60 min |

**Verification: CP-22**
```
pytest tests/analysis/test_trends.py -v              # 18 pass
pytest tests/analysis/test_performance.py -v         # 18 pass
# Manual: python -m cli.main log_trends --db-path ./test_frp_logs.db --days 7
# Verify JSON output has days[], summary, trend indicators
# Manual: python -m cli.main log_performance --db-path ./test_frp_logs.db
# Verify JSON output has entries[], sorted by success_rate
```

---

### Sprint 23: ConsolidationAnalyzer (4–5h)

**Goal:** Build A-01 — identify merge candidates across jobs.

| Task | File | Est. |
|------|------|------|
| Create `backend/analysis/consolidation.py` | ConsolidationAnalyzer class | 15 min |
| Implement `_extract_signature()` | (mailbox, parser, template) tuple | 30 min |
| Implement `_extract_unique_attributes()` | Per-job diff attributes | 20 min |
| Implement `_assess_merge_safety()` | safe/review/risky logic | 30 min |
| Implement `analyze()` | Full pipeline: group → filter → assess → report | 45 min |
| Create test fixtures | Mock parser with 10+ jobs, some sharing signatures | 20 min |
| Write tests: `test_consolidation.py` | 16 tests | 60 min |

**Verification: CP-23**
```
pytest tests/analysis/test_consolidation.py -v       # 16 pass
# Manual: python -m cli.main analyze_consolidation --settings-path ./test_settings.xml
# Verify groups found (or "no groups" for unique configs)
```

---

### Sprint 24: ImpactSimulator (5–7h)

**Goal:** Build A-02 — simulate impact of proposed changes.

| Task | File | Est. |
|------|------|------|
| Create `backend/analysis/impact.py` | ImpactSimulator class skeleton | 15 min |
| Implement `_sim_delete_job()` | Delete simulation with DID coverage check | 45 min |
| Implement `_sim_rename_did()` | Rename with collision detection | 30 min |
| Implement `_sim_change_filter()` | Filter change impact | 20 min |
| Implement `_sim_move_servicer()` | ServicerID migration impact | 30 min |
| Implement helper methods | `_check_recent_activity()`, `_calculate_risk()`, etc. | 20 min |
| Implement `simulate()` | Router to correct handler | 10 min |
| Create test fixtures | Mock parser, repo, analytics for each change type | 30 min |
| Write tests: `test_impact.py` | 22 tests (4 change types × 4-6 scenarios each) | 90 min |

**Verification: CP-24**
```
pytest tests/analysis/test_impact.py -v              # 22 pass
# Manual: python -m cli.main analyze_impact --change-type delete_job \
#         --target-job "Ocwen" --settings-path ./test_settings.xml
# Verify: affected entities, coverage delta, risk_level, recommendation
```

---

### Sprint 25: HealthChecker + CLI Commands (5–7h)

**Goal:** Build A-03 (the orchestrator) and wire all 5 Phase 4 commands to CLI.

| Task | File | Est. |
|------|------|------|
| Create `backend/analysis/health.py` | HealthChecker class | 15 min |
| Implement all 9 section checkers | One method per section | 90 min |
| Implement `check()` | Orchestrate sections, weighted scoring | 30 min |
| Implement graceful degradation | `_unavailable_section()`, `_error_section()` | 20 min |
| Add 5 CLI commands to `cli/main.py` | cmd_log_trends, cmd_log_performance, cmd_analyze_* | 45 min |
| Add argparse registrations | `add_phase4_commands()` | 20 min |
| Add error codes to `errors.py` | TREND-001/002, PERF-001, CONSOL-001, IMPACT-001 through 004, HEALTH-001 | 15 min |
| Write tests: `test_health.py` | 18 tests (9 sections × pass/fail + overall + degradation) | 75 min |
| Write tests: `test_main_p4.py` | 10 CLI integration tests | 45 min |

**Verification: CP-25**
```
pytest tests/analysis/test_health.py -v              # 18 pass
pytest tests/cli/test_main_p4.py -v                  # 10 pass
# Manual: python -m cli.main analyze_health --settings-path ./test_settings.xml \
#         --db-path ./test_frp_logs.db
# Verify: 9 sections, overall score, status
# Manual: python -m cli.main analyze_health (no args)
# Verify: Graceful degradation — unavailable sections shown as warning
```

---

### Sprint 26: Extension Handlers + Integration QA (4–5h)

**Goal:** Wire Phase 4 to Extension UI. Full end-to-end QA.

| Task | File | Est. |
|------|------|------|
| Create `extension/handlers/analyze.js` | handleAnalyze() with 3 subcommands | 30 min |
| Implement `parseChangeIntent()` | LLM-based intent parsing for /analyze impact | 30 min |
| Update `extension/handlers/logs.js` | Add `trends` and `performance` cases | 20 min |
| Register `/analyze` in `participant.js` | COMMAND_HANDLERS routing | 10 min |
| Register `/analyze` in `package.json` | chatParticipants.commands | 5 min |
| Add follow-up suggestions | PHASE4_FOLLOWUPS table | 20 min |
| F5 Extension Dev Host testing | 8 manual QA items (see below) | 45 min |
| Fix issues from QA | Bug fixes | 30 min |
| PyInstaller rebuild | Include analysis/ package in exe | 20 min |
| Update README | Phase 4 capabilities, all 6 slash commands | 15 min |

**Verification: CP-FINAL-P4**
```
pytest tests/ -v --tb=short                          # ALL Phase 1+2+3+4 tests pass
F5 → Extension Dev Host:
  @frp /logs trends                                  → 14-day trend timeline
  @frp /logs trends --days 30                        → 30-day trends
  @frp /logs performance                             → Ranked job table
  @frp /logs performance --top 5                     → Top 5 jobs
  @frp /analyze consolidation                        → Group report
  @frp /analyze impact delete job "Ocwen"            → Impact assessment
  @frp /analyze health                               → Full health report
  @frp /analyze health --type email                  → Email-only report
```

---

## 4. Verification Checkpoints

| Checkpoint | Sprint | Criteria |
|------------|--------|----------|
| CP-21 | 21 | All 13 model classes importable, serialization round-trips verified |
| CP-22 | 22 | TrendAnalyzer produces correct daily breakdowns with gap-filling; PerformanceBenchmarker ranks correctly with batch SQL |
| CP-23 | 23 | ConsolidationAnalyzer groups matching signatures, correctly classifies safe/review/risky |
| CP-24 | 24 | ImpactSimulator handles all 4 change types; coverage delta, risk_level, affected entities verified |
| CP-25 | 25 | HealthChecker produces 9 sections with weighted scoring; graceful degradation works when dependencies are None |
| CP-FINAL-P4 | 26 | All 5 Phase 4 use cases verified in F5 Extension Dev Host; all tests pass across all phases; PyInstaller build succeeds |

---

## 5. Rollback Strategy

| Sprint | If Fails… | Rollback To |
|--------|-----------|-------------|
| Sprint 21 | Models won't compile | Fix in place — pure dataclasses, no deps |
| Sprint 22 | SQL aggregation wrong | Fix queries; test data is in conftest. TrendAnalyzer and Benchmarker are independent |
| Sprint 23 | Signature extraction misgroups | Adjust _extract_signature(); covered by unit tests |
| Sprint 24 | Impact simulation inaccurate | Fix simulation handlers; each change_type is independent |
| Sprint 25 | Health scores incorrect | Adjust weights or score formulas; each section is independent |
| Sprint 26 | Extension integration issues | Phase 3 commands still work; Phase 4 is additive. Disable /analyze route if needed |

### Phase-Level Rollback

If Phase 4 cannot be completed:
- Phases 1–3 remain fully functional (26 use cases minus 5 = 21 use cases)
- Users lose `@frp /logs trends`, `@frp /logs performance`, and all `@frp /analyze` commands
- `@frp /logs health` (per-job health from Phase 3) still works as a lighter alternative to `/analyze health`
- No data loss — Phase 4 is purely read-only analysis

---

## 6. Minimum Viable Phase 4

If time is constrained, deliver in this order:

| Priority | Use Case | Rationale | Sprint |
|----------|----------|-----------|--------|
| 1 | A-03 (Full health check) | Highest overall value — single command shows system status | 25 |
| 2 | L-06 (Timeline trends) | Most requested daily-use feature — "is volume normal?" | 22 |
| 3 | L-07 (Job performance) | Identifies problem jobs for proactive action | 22 |
| 4 | A-01 (Consolidation) | Quarterly cleanup — less urgent than daily ops | 23 |
| 5 | A-02 (Impact simulation) | Pre-change safety — valuable but complex | 24 |

**Minimum viable Phase 4 = A-03 + L-06 + L-07** (Sprints 21, 22, 25 — skip 23/24)

This gives users the health dashboard and trends while deferring the less critical consolidation and impact simulation.

---

## Dependency Between Sprints

```
Sprint 21 (Models) ───────────────────────────┐
    │                                          │
    ├── Sprint 22 (Trends + Performance) ──────┤
    │                                          │
    ├── Sprint 23 (Consolidation) ─────────────┤
    │                                          │
    ├── Sprint 24 (Impact) ────────────────────┤
    │                                          │
    └──────────────────────────────────────────── Sprint 25 (Health + CLI)
                                                      │
                                                Sprint 26 (Extension + QA)
```

- Sprint 21 must come first (all others depend on models)
- Sprints 22, 23, 24 are **independent** of each other — can be done in any order
- Sprint 25 depends on Sprints 22–24 (HealthChecker uses PerformanceBenchmarker + all CLI commands)
- Sprint 26 depends on Sprint 25

---

*Next document: [05_TESTING_PLAN.md](05_TESTING_PLAN.md)*
