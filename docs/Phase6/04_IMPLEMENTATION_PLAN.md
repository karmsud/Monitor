# Phase 6: Implementation Plan
## FRP Agent — SQLite Job Cache + Multi-Agent Framework Retrofit

**Document Version:** 1.0  
**Date:** March 4, 2026  
**Status:** Planning  
**Companion:** [03_TECHNICAL_DESIGN.md](03_TECHNICAL_DESIGN.md)  
**Total Estimated Effort:** 12–16 hours across 6 sprints  
**Total New/Modified Files:** 24

---

## Table of Contents
1. [Implementation Principles](#implementation-principles)  
2. [Phase Gate Prerequisites](#phase-gate-prerequisites)  
3. [Sprint Plan](#sprint-plan)  
4. [Verification Checkpoints](#verification-checkpoints)  
5. [Sprint Details](#sprint-details)  
6. [Rollback Strategy](#rollback-strategy)  
7. [Post-Implementation Validation](#post-implementation-validation)

---

## Implementation Principles

1. **SQLite first, framework second.** Build the cache layer so that framework files describe the final state of the system.
2. **Test as you go.** Each sprint ends with all tests passing. Never proceed with a red suite.
3. **Preserve interfaces.** CLI JSON shapes must not change. The extension is untouched.
4. **Fallback by default.** The SQLite cache is optional — if absent, the system works as before.
5. **Additive only.** No existing code is deleted. New code is added; existing code is wrapped.
6. **One sprint = one coherent deliverable.** Each sprint produces a usable checkpoint.

---

## Phase Gate Prerequisites

Before starting Sprint 1, verify:

| # | Prerequisite | Verification |
|---|---|---|
| PG-1 | Phase 5 complete | `pytest tests/ -q` → 655+ passed, 0 failed |
| PG-2 | Triage cross-ref complete | `test_analyzer_crossref.py` → 29 passed |
| PG-3 | Python 3.13.5 + .venv | `python --version` |
| PG-4 | SQLite available | `python -c "import sqlite3; print(sqlite3.sqlite_version)"` |
| PG-5 | Settings.xml accessible | Email and SFTP Settings.xml files exist and parse correctly |
| PG-6 | MySQL running | `frp_database` on `localhost:3306` |

---

## Sprint Plan

| Sprint | Name | Work Stream | Est. Hours | Files | Checkpoint |
|---|---|---|---|---|---|
| S1 | SQLite Schema + XmlJobIndex | WS-A | 2–3h | 2 new | CP-61 |
| S2 | CLI Integration | WS-A | 2–3h | 1 modified | CP-62 |
| S3 | SQLite Tests | WS-A | 1–2h | 1 new | CP-63 |
| S4 | Framework Core | WS-B | 2–3h | 6 new, 1 rewrite | CP-64 |
| S5 | Skill Packs + Prompts | WS-B | 2–3h | 14 new | CP-65 |
| S6 | Integration Validation | Both | 1–2h | 0 | CP-66 |

---

## Verification Checkpoints

| # | After Sprint | Verification | Command |
|---|---|---|---|
| CP-61 | S1 | `XmlJobIndex` module parses XML and populates SQLite | `python -c "from backend.db.xml_index import XmlJobIndex"` |
| CP-62 | S2 | CLI commands work with and without `--cache-db-path` | `python -m cli.main search_jobs --query "fay" --settings-path Settings.xml` |
| CP-63 | S3 | All new + existing tests pass | `pytest tests/ -q` → 680+ passed, 0 failed |
| CP-64 | S4 | Framework files valid; Copilot loads `AGENTS.md` | Manual: open VS Code, verify agent list |
| CP-65 | S5 | All skill and prompt files created; VS Code prompt picker populated | Manual: VS Code agent/prompt verification |
| CP-66 | S6 | Full suite, end-to-end cache rebuild, framework file scan | `pytest tests/ -q` + manual validation |

---

## Sprint Details

### Sprint 1: SQLite Schema + XmlJobIndex (2–3h)

**Goal:** Create the `XmlJobIndex` class with full rebuild, search, and hash capabilities.

| # | Task | File | Est. |
|---|---|---|---|
| S1-1 | Create `backend/db/xml_index.py` with schema constants | `backend/db/xml_index.py` | 15m |
| S1-2 | Implement `__init__`, `_create_tables`, WAL mode | `backend/db/xml_index.py` | 15m |
| S1-3 | Implement `rebuild()` for email jobs | `backend/db/xml_index.py` | 30m |
| S1-4 | Implement `rebuild()` for SFTP jobs | `backend/db/xml_index.py` | 20m |
| S1-5 | Implement `_compute_config_hash()` | `backend/db/xml_index.py` | 15m |
| S1-6 | Implement `search_jobs()` with LIKE + tokenized match | `backend/db/xml_index.py` | 30m |
| S1-7 | Implement `get_job()`, `get_all_jobs()` | `backend/db/xml_index.py` | 15m |
| S1-8 | Implement `check_hash()`, `get_status()` | `backend/db/xml_index.py` | 10m |
| S1-9 | Implement row-to-dict converters (summary + detail) | `backend/db/xml_index.py` | 20m |
| S1-10 | Implement `close()`, `__enter__`, `__exit__` | `backend/db/xml_index.py` | 5m |
| S1-11 | Update `backend/db/__init__.py` exports | `backend/db/__init__.py` | 2m |
| S1-12 | Fix Phase 5 hidden imports in `frp_backend.spec` | `packaging/frp_backend.spec` | 5m |

**Checkpoint CP-61:** Import `XmlJobIndex`, instantiate with `:memory:`, call `rebuild()` on a test XML.

---

### Sprint 2: CLI Integration (2–3h)

**Goal:** Wire `XmlJobIndex` into existing CLI commands with fallback to XML.

| # | Task | File | Est. |
|---|---|---|---|
| S2-1 | Add `_xml_index_from_args()` helper | `cli/main.py` | 10m |
| S2-2 | Add `_rebuild_sqlite()` helper | `cli/main.py` | 10m |
| S2-3 | Modify `cmd_search_jobs` — try SQLite first, fallback to XML | `cli/main.py` | 30m |
| S2-4 | Modify `cmd_job_detail` — try SQLite first, fallback to XML | `cli/main.py` | 30m |
| S2-5 | Modify `cmd_create_job` — add `_rebuild_sqlite()` after write | `cli/main.py` | 5m |
| S2-6 | Modify `cmd_edit_job` — add `_rebuild_sqlite()` after write | `cli/main.py` | 5m |
| S2-7 | Add `cmd_rebuild_db` command handler | `cli/main.py` | 15m |
| S2-8 | Add `rebuild_db` to `COMMAND_HANDLERS` dict | `cli/main.py` | 2m |
| S2-9 | Add argparse subparser for `rebuild_db` | `cli/main.py` | 10m |
| S2-10 | Add `--cache-db-path` global argument | `cli/main.py` | 5m |
| S2-11 | Verify existing commands still work without `--cache-db-path` | Manual test | 10m |
| S2-12 | Add Phase 6 hidden import to `frp_backend.spec` | `packaging/frp_backend.spec` | 2m |
| S2-13 | Add `frpAgent.cacheDbPath` setting to `extension/package.json` | `extension/package.json` | 5m |

**Checkpoint CP-62:** Run `search_jobs` with and without `--cache-db-path`. Both produce valid JSON.

---

### Sprint 3: SQLite Tests (1–2h)

**Goal:** Create comprehensive tests for `XmlJobIndex`.

| # | Task | File | Est. |
|---|---|---|---|
| S3-1 | Create test file with fixtures (in-memory SQLite, mock XML) | `tests/db/test_xml_index.py` | 15m |
| S3-2 | Test schema creation (tables, indexes, metadata) | `tests/db/test_xml_index.py` | 10m |
| S3-3 | Test `rebuild()` for email jobs (count, hash stored) | `tests/db/test_xml_index.py` | 15m |
| S3-4 | Test `rebuild()` for SFTP jobs (count, hash stored) | `tests/db/test_xml_index.py` | 15m |
| S3-5 | Test `search_jobs()` — basic match, no match, multi-token | `tests/db/test_xml_index.py` | 20m |
| S3-6 | Test `get_job()` — found (email), found (sftp), not found | `tests/db/test_xml_index.py` | 15m |
| S3-7 | Test `get_all_jobs()` — email, sftp, all | `tests/db/test_xml_index.py` | 10m |
| S3-8 | Test `check_hash()` — fresh, stale | `tests/db/test_xml_index.py` | 15m |
| S3-9 | Test `get_status()` — counts, hash values | `tests/db/test_xml_index.py` | 10m |
| S3-10 | Test content hash excludes `last_run_time` | `tests/db/test_xml_index.py` | 15m |
| S3-11 | Test row-to-summary format matches EmailJob.to_summary_dict() | `tests/db/test_xml_index.py` | 15m |
| S3-12 | Test context manager (`with` statement) | `tests/db/test_xml_index.py` | 5m |
| S3-13 | Run full suite — all existing tests still pass | `pytest tests/ -q` | 5m |

**Checkpoint CP-63:** `pytest tests/ -q` → 680+ passed, 0 failed. New tests: ~25–35.

---

### Sprint 4: Framework Core (2–3h)

**Goal:** Create the foundation framework files — copilot-instructions.md (rewrite), AGENTS.md, 4 agent files, 3 instructions.md files.

| # | Task | File | Est. |
|---|---|---|---|
| S4-1 | Rewrite `.github/copilot-instructions.md` — prescriptive rules | `.github/copilot-instructions.md` | 30m |
| S4-2 | Create `AGENTS.md` — operating manual | `AGENTS.md` | 25m |
| S4-3 | Create `.github/agents/config.agent.md` | `.github/agents/config.agent.md` | 20m |
| S4-4 | Create `.github/agents/triage.agent.md` | `.github/agents/triage.agent.md` | 15m |
| S4-5 | Create `.github/agents/intel.agent.md` | `.github/agents/intel.agent.md` | 15m |
| S4-6 | Create `.github/agents/ops.agent.md` | `.github/agents/ops.agent.md` | 15m |
| S4-7 | Create `backend.instructions.md` | `backend.instructions.md` | 10m |
| S4-8 | Create `extension.instructions.md` | `extension.instructions.md` | 10m |
| S4-9 | Create `cli.instructions.md` | `cli.instructions.md` | 10m |

**Checkpoint CP-64:** Open VS Code. Verify agent list shows config, triage, intel, ops in agent selector (if supported). Verify `AGENTS.md` renders correctly.

---

### Sprint 5: Skill Packs + Prompts (2–3h)

**Goal:** Create all skill pack files and prompt launcher files.

| # | Task | File | Est. |
|---|---|---|---|
| S5-1 | Create `skills/xml-config/SKILL.md` | `skills/xml-config/SKILL.md` | 20m |
| S5-2 | Create `skills/email-triage/SKILL.md` | `skills/email-triage/SKILL.md` | 15m |
| S5-3 | Create `skills/deal-intelligence/SKILL.md` | `skills/deal-intelligence/SKILL.md` | 15m |
| S5-4 | Create `skills/log-forensics/SKILL.md` | `skills/log-forensics/SKILL.md` | 15m |
| S5-5 | Create `skills/template-staging/SKILL.md` | `skills/template-staging/SKILL.md` | 15m |
| S5-6 | Create `.github/prompts/search-jobs.prompt.md` | `.github/prompts/search-jobs.prompt.md` | 8m |
| S5-7 | Create `.github/prompts/triage-email.prompt.md` | `.github/prompts/triage-email.prompt.md` | 8m |
| S5-8 | Create `.github/prompts/staging-lookup.prompt.md` | `.github/prompts/staging-lookup.prompt.md` | 8m |
| S5-9 | Create `.github/prompts/deploy-diff.prompt.md` | `.github/prompts/deploy-diff.prompt.md` | 8m |
| S5-10 | Create `.github/prompts/health-check.prompt.md` | `.github/prompts/health-check.prompt.md` | 8m |
| S5-11 | Create `.github/prompts/deal-lookup.prompt.md` | `.github/prompts/deal-lookup.prompt.md` | 8m |

**Checkpoint CP-65:** All 14 files created. VS Code prompt picker shows all 6 prompts. Skill files render correctly in markdown preview.

---

### Sprint 6: Integration Validation (1–2h)

**Goal:** End-to-end validation of both work streams together.

| # | Task | Details | Est. |
|---|---|---|---|
| S6-1 | Run full pytest suite | All 680+ tests pass | 10m |
| S6-2 | Test `rebuild_db` with real Settings.xml (email) | Verify SQLite contains correct job count | 10m |
| S6-3 | Test `rebuild_db` with real Settings.xml (SFTP) | Verify SQLite contains correct job count | 10m |
| S6-4 | Test `search_jobs` with cache vs without cache | Compare results — must be identical | 15m |
| S6-5 | Test `job_detail` with cache vs without cache | Compare results — must be identical | 15m |
| S6-6 | Test hash freshness — modify XML, verify stale detected | Content hash changes after config edit | 10m |
| S6-7 | Test hash stability — modify `last_run_time`, verify NOT stale | Content hash unchanged | 10m |
| S6-8 | Verify framework files in VS Code | Agents, prompts, skills visible | 10m |
| S6-9 | Verify extension still works | All 7 slash commands functional | 10m |
| S6-10 | Update `docs/Phase6/` with final results | Document actual test counts, any adjustments | 10m |

**Checkpoint CP-66:** Full green suite. Cache produces identical results to XML parsing. Framework files load correctly. Extension unchanged.

---

## Rollback Strategy

### WS-A: SQLite Cache

If the cache layer causes issues:
1. Remove `--cache-db-path` argument from CLI invocations
2. All commands revert to XML parsing (fallback code is permanent)
3. Delete `frp_xml_cache.db` file
4. No code changes needed — the fallback path is always present

### WS-B: Framework Retrofit

If framework files cause Copilot confusion:
1. Delete individual `.agent.md` or `.prompt.md` files
2. Copilot falls back to `copilot-instructions.md` (always present)
3. No code changes needed — files are purely declarative

**Risk level:** Minimal. Both work streams are additive and independently removable.

---

## Post-Implementation Validation

### Automated
```bash
# All tests pass
pytest tests/ -q

# Module importable
python -c "from backend.db.xml_index import XmlJobIndex; print('OK')"

# Rebuild works
python -m cli.main rebuild_db --cache-db-path frp_xml_cache.db --settings-path Settings.xml --xml-type email
```

### Manual
- [ ] `@frp /jobs search fay` returns results (extension)
- [ ] `@frp /jobs detail CMLTI_Fay_100` returns detail (extension)
- [ ] Agent selector shows config, triage, intel, ops
- [ ] Prompt picker shows all 6 prompt files
- [ ] Modify Settings.xml → `search_jobs` reports stale warning
- [ ] Run `rebuild_db` → stale warning clears
- [ ] Modify `last_run_time` in XML → no stale warning (hash stable)

### Coverage Target
- Existing tests: 655 → continue passing
- New tests (SQLite): 25–35
- **Total target: 680–690 passed, 0 failed**
