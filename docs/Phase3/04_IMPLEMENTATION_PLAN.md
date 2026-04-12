# Phase 3: Implementation Plan
## FRP Agent — Log Analytics & Email Triage Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Total Sprints:** 6 (Sprints 15–20)  
**Estimated Hours:** 25–33 hours  

---

## Table of Contents
1. [Implementation Principles](#1-implementation-principles)
2. [Phase 2 Gate](#2-phase-2-gate)
3. [Sprint Plan](#3-sprint-plan)
4. [Verification Checkpoints](#4-verification-checkpoints)
5. [Rollback Strategy](#5-rollback-strategy)
6. [Minimum Viable Phase 3](#6-minimum-viable-phase-3)

---

## 1. Implementation Principles

1. **Log analytics first, triage second** — Log analytics uses existing SQLite infrastructure; triage requires a new pip dependency (`extract-msg`) and new module.
2. **Test each query in isolation** — Every SQLite query in analytics.py gets a dedicated unit test with controlled data.
3. **Mock .msg files for testing** — Create minimal .msg test fixtures rather than requiring real Outlook files.
4. **Privacy by design** — Email body content is never sent to the LLM. Only `to_safe_dict()` metadata is used.
5. **Progressive enhancement** — Triage works without DB (match-only mode), but is richer with DB (DID verification).

---

## 2. Phase 2 Gate

Before starting Phase 3:

| Prerequisite | Verification |
|-------------|--------------|
| Phase 2 CP-FINAL-P2 passed | All 8 Phase 2 UCs work in Extension Dev Host |
| SQLite index has test data | `frp_logs.db` exists with ≥100 sample events |
| `extract-msg` installs in venv | `pip install extract-msg` succeeds on target Python |
| `extract-msg` bundles in exe | PyInstaller test build includes extract-msg |
| Sample .msg files available | 3+ test .msg files or mock fixtures ready |

---

## 3. Sprint Plan

### Sprint 15: Log + Triage Data Models (3–4h)

**Goal:** Create all Phase 3 data models and the .msg parser.

| Task | File | Est. |
|------|------|------|
| Create `backend/logs/models.py` | DealActivity, DIDFailure, JobHealth, DailySummary | 30 min |
| Create `backend/triage/__init__.py` | Empty init | 5 min |
| Create `backend/triage/models.py` | EmailInfo, MatchResult, TriageResult | 45 min |
| Create `backend/triage/msg_parser.py` | MsgParser.parse() with extract-msg | 60 min |
| Install `extract-msg` in venv | `pip install extract-msg` | 10 min |
| Write tests: `test_log_models.py` | 12 tests (serialization, edge cases) | 30 min |
| Write tests: `test_triage_models.py` | 15 tests (EmailInfo, MatchResult, TriageResult) | 30 min |
| Write tests: `test_msg_parser.py` | 14 tests (parse, errors, edge cases) | 45 min |

**Verification: CP-15**
```
pytest tests/logs/test_log_models.py -v         # 12 pass
pytest tests/triage/test_triage_models.py -v     # 15 pass
pytest tests/triage/test_msg_parser.py -v        # 14 pass (with mock .msg fixtures)
```

---

### Sprint 16: Log Analytics Engine (5–7h)

**Goal:** Build the full LogAnalytics class with all 4 query methods.

| Task | File | Est. |
|------|------|------|
| Create `backend/logs/analytics.py` | LogAnalytics class skeleton | 30 min |
| Implement `check_staleness()` | Query sync_meta | 20 min |
| Implement `deal_activity()` | L-02 query | 45 min |
| Implement `did_failures()` | L-03 aggregation | 45 min |
| Implement `job_health()` | L-04 metrics computation | 60 min |
| Implement `daily_summary()` | L-05 dashboard | 60 min |
| Create SQLite test fixtures | conftest.py: populate test DB | 30 min |
| Write tests: `test_analytics.py` | 32 tests across all methods | 90 min |

**Verification: CP-16**
```
pytest tests/logs/test_analytics.py -v           # 32 pass
# Manual: python -m cli.main log_daily_summary --db-path ./test_frp_logs.db
# Verify JSON output matches expected format
```

---

### Sprint 17: Email Triage Matcher (5–7h)

**Goal:** Build matcher.py and integrate with analyzer.py for E-01 and E-02.

| Task | File | Est. |
|------|------|------|
| Create `backend/triage/matcher.py` | TriageMatcher class | 60 min |
| Implement `_extract_filters()` | Parse job filter configs | 30 min |
| Implement `_assess_confidence()` | Exact vs partial | 20 min |
| Implement `match()` method | Full matching pipeline | 45 min |
| Create `backend/triage/analyzer.py` | TriageAnalyzer skeleton | 15 min |
| Implement `verify()` method | E-01 pipeline | 45 min |
| Implement `match_only()` method | E-02 pipeline | 30 min |
| Write tests: `test_matcher.py` | 18 tests | 60 min |
| Write tests: `test_analyzer_verify.py` | 10 tests for E-01 | 45 min |
| Write tests: `test_analyzer_match.py` | 6 tests for E-02 | 30 min |

**Verification: CP-17**
```
pytest tests/triage/test_matcher.py -v           # 18 pass
pytest tests/triage/test_analyzer_verify.py -v   # 10 pass
pytest tests/triage/test_analyzer_match.py -v    # 6 pass
# Manual: python -m cli.main triage_match --sender "test@bank.com" --settings-path ./test_settings.xml
```

---

### Sprint 18: No-Match Analyzer + LLM Integration (4–5h)

**Goal:** Complete analyzer.py for E-03 and add DealRepository methods.

| Task | File | Est. |
|------|------|------|
| Implement `analyze_new()` method | E-03 full pipeline | 60 min |
| Implement `_guess_parser()` | Attachment-based parser hint | 20 min |
| Implement `_extract_subject_pattern()` | Subject → filter pattern | 20 min |
| Add `resolve_did_by_name()` to DealRepository | DB addition | 30 min |
| Add `get_companies_by_sender_domain()` to DealRepository | DB addition | 20 min |
| Add error codes to `errors.py` | LOG-001 through TRIAGE-001 | 15 min |
| Write tests: `test_analyzer_new.py` | 16 tests | 60 min |
| Write tests: `test_deal_repo_p3.py` | 8 tests | 30 min |

**Verification: CP-18**
```
pytest tests/triage/test_analyzer_new.py -v      # 16 pass
pytest tests/db/test_deal_repo_p3.py -v          # 8 pass
# Manual: python -m cli.main triage_new --msg-path ./test.msg --settings-path ./test_settings.xml
```

---

### Sprint 19: CLI + Extension Handlers (4–5h)

**Goal:** Wire Phase 3 backend to CLI commands and Extension UI.

| Task | File | Est. |
|------|------|------|
| Add Phase 3 CLI commands to `main.py` | 7 cmd_* functions + argparse | 60 min |
| Update `/logs` handler | deal, failures, health, summary subcommands | 45 min |
| Create `/triage` handler | verify, match, new subcommands | 45 min |
| Add `extractMsgPath()` utility | .msg path detection | 15 min |
| Register `/triage` in package.json | New slash command | 10 min |
| Add follow-up suggestions | Post-command suggestions | 20 min |
| Add stale index warning display | Extension warning logic | 15 min |
| Write CLI tests: `test_main_p3.py` | 14 tests | 60 min |

**Verification: CP-19**
```
pytest tests/cli/test_main_p3.py -v              # 14 pass
# CLI: python -m cli.main log_daily_summary --db-path ./frp_logs.db
# CLI: python -m cli.main triage_verify --msg-path ./test.msg --settings-path ...
```

---

### Sprint 20: Integration Testing + Manual QA (4–5h)

**Goal:** Full integration testing and F5 manual QA.

| Task | File | Est. |
|------|------|------|
| End-to-end log analytics pipeline | All 4 log commands | 45 min |
| End-to-end triage pipeline | All 3 triage commands | 45 min |
| F5 Extension Dev Host testing | 12 manual QA items | 60 min |
| Test stale index warning | Age the sync_meta timestamp | 15 min |
| Test .msg file parsing in exe | PyInstaller build test | 30 min |
| Fix issues from QA | Bug fixes | 30 min |
| Update project README | Phase 3 capabilities | 15 min |

**Verification: CP-FINAL-P3**
```
pytest tests/ -v --tb=short                      # All Phase 1+2+3 tests pass
F5 → Extension Dev Host:
  @frp /logs deal CSFB                           → Timeline shown
  @frp /logs failures                            → Failure table shown
  @frp /logs health rptent                       → Health dashboard shown
  @frp /logs summary                             → Daily dashboard shown
  @frp /triage verify test.msg                   → Verification result shown
  @frp /triage match test.msg                    → Ranked matches shown
  @frp /triage new test.msg                      → Template suggestion shown
```

---

## 4. Verification Checkpoints

| Checkpoint | Sprint | Criteria |
|------------|--------|----------|
| CP-15 | 15 | All data models importable, .msg parser works with mock fixtures |
| CP-16 | 16 | All 4 log analytics queries return correct data from test SQLite DB |
| CP-17 | 17 | Matcher finds correct jobs for test emails; verify/match E-01/E-02 work |
| CP-18 | 18 | No-match analyzer suggests templates; DB resolve methods work |
| CP-19 | 19 | All 7 CLI commands return valid JSON; Extension handlers route correctly |
| CP-FINAL-P3 | 20 | All 7 Phase 3 use cases verified in F5 Extension Dev Host; all tests pass |

---

## 5. Rollback Strategy

| Sprint | If Fails… | Rollback To |
|--------|-----------|-------------|
| Sprint 15 | Models/parser won't compile | Fix in place — no dependencies |
| Sprint 16 | SQLite queries return wrong data | Fix queries; test data is in conftest |
| Sprint 17 | Matcher false positives | Adjust matching logic; covered by unit tests |
| Sprint 18 | extract-msg parsing failures | Fall back to manual sender/subject input (E-02 path) |
| Sprint 19 | CLI/Extension integration issues | Phase 2 commands still work; Phase 3 isolated |
| Sprint 20 | QA failures | Fix issues; re-run checkpoint |

---

## 6. Minimum Viable Phase 3

If time is constrained, deliver in this priority order:

| Priority | Use Cases | Rationale |
|----------|-----------|-----------|
| 1 | L-05 (daily summary) | Highest daily operational value |
| 2 | L-03 (DID failures) | Direct impact on error resolution |
| 3 | L-04 (job health) | Proactive monitoring |
| 4 | L-02 (deal activity) | Investigation support |
| 5 | E-01 (verify) | Most common triage action |
| 6 | E-02 (match) | Search capability |
| 7 | E-03 (new) | Least common, depends on Phase 2 CRUD |

**Minimum viable = L-05 + L-03 + L-04 + L-02** (log analytics only, 4 sprints)

---

*Next document: [05_TESTING_PLAN.md](05_TESTING_PLAN.md)*
