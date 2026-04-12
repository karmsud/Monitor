# Phase 6: Executive Summary
## FRP Agent — SQLite Job Cache + Multi-Agent Framework Retrofit

**Document Version:** 1.0  
**Date:** March 4, 2026  
**Status:** Planning  
**Phase Scope:** SQLite config cache for Settings.xml queries, Copilot multi-agent file hierarchy retrofit  
**Work Streams:** WS-A (SQLite Cache) + WS-B (Framework Retrofit)  
**Prerequisites:** Phase 1–5 complete and verified (655 tests passing)

---

## Table of Contents
1. [Executive Overview](#executive-overview)  
2. [Business Context](#business-context)  
3. [Phase 6 Objectives](#phase-6-objectives)  
4. [Work Stream Breakdown](#work-stream-breakdown)  
5. [Architecture Decision Records](#architecture-decision-records)  
6. [Risk Assessment](#risk-assessment)  
7. [Success Criteria](#success-criteria)  
8. [Dependencies & Prerequisites](#dependencies--prerequisites)  
9. [Why Not a Rewrite](#why-not-a-rewrite)  
10. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Does Phase 6 Add?

Phase 6 is a **dual-track infrastructure upgrade** that improves two distinct layers of the FRP Agent without altering any existing features or API contracts:

**Work Stream A – SQLite Job Config Cache:**  
Settings.xml (48+ email jobs, 20+ SFTP jobs) is currently parsed from raw XML on every query. This adds a SQLite cache layer that pre-indexes all job configurations for instant querying, while XML remains the authoritative runtime file. PowerShell continues to own `last_run_time` exclusively.

**Work Stream B – Multi-Agent Framework Retrofit:**  
The codebase currently relies on a single `copilot-instructions.md` file and a monolith chat participant. This adds the full Copilot multi-agent file hierarchy — `AGENTS.md`, `.agent.md` personas, `SKILL.md` capability packs, and `.prompt.md` task launchers — to make the system self-documenting and Copilot-native.

### Why Combine Them?

These work streams occupy **different layers of the stack** with zero overlap:

| Work Stream | Layer | Touches |
|---|---|---|
| WS-A: SQLite Cache | Data access (bottom) | `backend/db/`, `cli/main.py` internals |
| WS-B: Framework Retrofit | Declarative metadata (top) | `.github/`, `skills/`, markdown only |

Doing them together means the framework files describe the system **as it will be** — including the SQLite cache — rather than requiring updates a week later. A new developer inheriting the project sees accurate documentation from day one.

### What Changes for Existing Users?

**Nothing.** Every existing slash command, CLI command, and extension handler continues to work identically. The test suite (655 tests) continues to pass. The upgrade is purely internal:

- `@frp /jobs search fay` returns the same results, but the CLI backend reads from SQLite instead of parsing XML
- `@frp /jobs detail CMLTI_Fay` returns the same JSON shape
- `@frp /deploy save` writes XML and triggers a one-line SQLite rebuild
- All `@frp /triage`, `/deals`, `/logs`, `/analyze`, `/staging` commands are untouched

---

## Business Context

### Problem Phase 6 Solves

| Problem | Current State | Phase 6 Solution |
|---|---|---|
| **XML re-parsing overhead** | Every `search_jobs`/`job_detail` call re-parses full XML from disk | SQLite cache: parse once, query instantly |
| **No correctness guarantee** | If XML is edited outside the agent, no detection | Content hash on config fields (excluding `last_run_time`) detects drift |
| **Tribal knowledge locked in conversations** | Design rules, SFTP filename-only matching, `last_run_time` ownership — all undocumented | Externalised into `.agent.md`, `SKILL.md`, `AGENTS.md` files |
| **Monolith participant** | One 3,000+ line JS file handles all personas | Framework files define agent boundaries; participant refactor is optional future work |
| **No standardised onboarding** | New developer must read all conversations to understand the system | Framework files + prompt files make Copilot understand the project natively |
| **No repeatable task launchers** | Common workflows (triage, search, staging) require knowing slash commands | `.prompt.md` files provide named, discoverable entry points |

### Who Benefits?

| Persona | Benefit |
|---|---|
| **Current Developer (You)** | SQLite queries are faster; framework files document decisions you've made |
| **Future Developer (Handoff)** | Copilot immediately understands agent roles, operating rules, and domain skills |
| **PowerShell Script** | Zero change — continues to own `last_run_time`, reads/writes XML as before |
| **ActiveBatch Scheduler** | Zero change — EmailMonitor.ps1 workflow unchanged |

---

## Phase 6 Objectives

### WS-A: SQLite Job Config Cache

| ID | Objective | Deliverable |
|---|---|---|
| A-1 | SQLite schema for email and SFTP jobs | Two tables: `email_jobs`, `sftp_jobs` with all config fields |
| A-2 | Rebuild engine | `XmlJobIndex.rebuild()` — parse XML, populate SQLite, compute content hash |
| A-3 | Query interface | `XmlJobIndex.search_jobs(query)`, `.get_job(name)`, `.get_all_jobs()` |
| A-4 | Hash-based correctness check | On every query, compare stored hash vs live XML hash; warn if stale |
| A-5 | CLI `rebuild_db` command | Explicit `frp xml rebuild-db` for bootstrap/recovery |
| A-6 | Rewire `cmd_search_jobs` | Internal swap: XML parse → SQLite query. Same interface. |
| A-7 | Rewire `cmd_job_detail` | Internal swap: XML parse → SQLite query. Same interface. |
| A-8 | Write-then-rebuild pattern | `cmd_create_job` and `cmd_edit_job` call `_rebuild_sqlite()` after XML write |
| A-9 | TriageAnalyzer optimisation | One-line change: `TriageAnalyzer.__init__` can read from cache instead of XML |

### WS-B: Multi-Agent Framework Retrofit

| ID | Objective | Deliverable |
|---|---|---|
| B-1 | Rewrite `copilot-instructions.md` | Prescriptive rules (not descriptive documentation) |
| B-2 | Create `AGENTS.md` | Agent operating rules — validation, testing, field ownership |
| B-3 | Create agent personas | 4 `.agent.md` files: config, triage, intel, ops |
| B-4 | Create skill packs | 5 `SKILL.md` files: xml-config, email-triage, deal-intelligence, log-forensics, template-staging |
| B-5 | Create prompt files | 6 `.prompt.md` files for common workflows |
| B-6 | Create `.instructions.md` files | Path-specific rules for `backend/`, `extension/`, `cli/` |

---

## Work Stream Breakdown

### WS-A: SQLite Cache — Layer Diagram

```
┌─────────────────────────────────────────────────────────┐
│  Extension JS  (participant.js)                         │
│  backendCall('search_jobs', {query: "fay"})             │
│  ← receives same JSON shape, zero changes               │
├─────────────────────────────────────────────────────────┤
│  CLI  (cli/main.py)                                     │
│  cmd_search_jobs()    ← internal: SQLite query           │
│  cmd_job_detail()     ← internal: SQLite query           │
│  cmd_create_job()     ← add: _rebuild_sqlite() after     │
│  cmd_edit_job()       ← add: _rebuild_sqlite() after     │
├─────────────────────────────────────────────────────────┤
│  NEW: backend/db/xml_index.py                           │
│  XmlJobIndex class                                      │
│  - rebuild(xml_path, xml_type) → parse XML → SQLite     │
│  - search_jobs(query) → List[Dict]                      │
│  - get_job(name) → Dict | None                          │
│  - get_all_jobs() → List[Dict]                          │
│  - check_hash() → bool (stale detection)                │
├─────────────────────────────────────────────────────────┤
│  EXISTING: backend/xml/parser.py  (UNTOUCHED)           │
│  SettingsXmlParser  ← still used by crud, diff, rollback │
│  EmailJob / SftpJob models  ← still the canonical types  │
├─────────────────────────────────────────────────────────┤
│  Settings.xml  (Source of truth — PowerShell owns)      │
│  last_run_time updated every ~10 minutes by PS          │
└─────────────────────────────────────────────────────────┘
```

### WS-B: Framework Retrofit — File Tree

```
.github/
├── copilot-instructions.md          ← REWRITE (prescriptive rules)
├── agents/
│   ├── config.agent.md              ← NEW (XML config persona)
│   ├── triage.agent.md              ← NEW (email triage persona)
│   ├── intel.agent.md               ← NEW (deal intelligence persona)
│   └── ops.agent.md                 ← NEW (operations/analytics persona)
├── prompts/
│   ├── search-jobs.prompt.md        ← NEW
│   ├── triage-email.prompt.md       ← NEW
│   ├── staging-lookup.prompt.md     ← NEW
│   ├── deploy-diff.prompt.md        ← NEW
│   ├── health-check.prompt.md       ← NEW
│   └── deal-lookup.prompt.md        ← NEW
AGENTS.md                            ← NEW (root-level operating rules)
backend.instructions.md              ← NEW (Python backend rules)
extension.instructions.md            ← NEW (Extension JS rules)
cli.instructions.md                  ← NEW (CLI rules)
skills/
├── xml-config/
│   └── SKILL.md                     ← NEW
├── email-triage/
│   └── SKILL.md                     ← NEW
├── deal-intelligence/
│   └── SKILL.md                     ← NEW
├── log-forensics/
│   └── SKILL.md                     ← NEW
└── template-staging/
    └── SKILL.md                     ← NEW
```

---

## Architecture Decision Records

### ADR-1: SQLite Is Config-Only Cache, XML Remains Live

**Context:** Settings.xml is modified by both the FRP Agent (surgical edits) and the PowerShell EmailMonitor (every ~10 minutes for `last_run_time`).  
**Decision:** SQLite is a read-only query cache for config fields. XML remains the authoritative file. PowerShell never sees SQLite.  
**Consequence:** Agent must rebuild SQLite after any XML write. Content hash (config fields only, excluding `last_run_time`) ensures passive correctness.

### ADR-2: Two Separate Tables, Not One

**Context:** EmailJob and SftpJob have different schemas (mailbox vs. path, filters vs. skip_list).  
**Decision:** Two tables: `email_jobs` and `sftp_jobs`. Unified query methods abstract over both.  
**Consequence:** Schema is clean and type-safe. Cross-type searches iterate both tables.

### ADR-3: Hash Excludes `last_run_time`

**Context:** PowerShell updates `last_run_time` every ~10 minutes. Hashing the entire XML would always report "stale."  
**Decision:** Hash computation strips `last_run_time` elements before hashing. Config changes are detected; operational timestamps are ignored.  
**Consequence:** Hash comparison is a reliable correctness check, not a false-positive generator.

### ADR-4: Retrofit, Not Rewrite

**Context:** Colleague suggested adopting the multi-agent file hierarchy framework.  
**Decision:** Add the framework's declarative layer on top of the existing codebase. No code rewrite.  
**Consequence:** 655 tests stay valid. All existing features preserved. Framework files are additive-only.

### ADR-5: Framework Files Describe Post-Cache Architecture

**Context:** SQLite cache and framework retrofit are being done together.  
**Decision:** Agent files, skill docs, and operating rules describe the system with the SQLite cache in place.  
**Consequence:** No second documentation pass needed. Files are accurate from day one.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SQLite rebuild fails silently | Low | Medium | Every query checks content hash; stale = warning + XML fallback |
| Framework files confuse Copilot | Low | Low | Follow exact official file naming patterns; test in Dev Host |
| `cmd_search_jobs` regression | Low | High | Existing tests cover interface; add SQLite-specific tests |
| PowerShell modifies config fields | Very Low | Medium | Content hash detects; `rebuild-db` recovers |
| `participant.js` split introduces bugs | Medium | Medium | Deferred to optional future phase; framework works without it |

---

## Success Criteria

| Criterion | Measurement |
|---|---|
| All 655 existing tests pass | `pytest tests/ -q` → 655+ passed, 0 failed |
| New SQLite tests pass | ~25–35 new tests in `tests/db/test_xml_index.py` |
| `frp xml rebuild-db` works | CLI command creates/refreshes SQLite from XML |
| `cmd_search_jobs` returns identical results | Same JSON shape, same jobs, from SQLite instead of XML |
| `cmd_job_detail` returns identical results | Same JSON shape, same cross-references |
| Hash check detects config changes | Modify a job field in XML → query reports stale warning |
| Hash check ignores `last_run_time` | Modify `last_run_time` in XML → no stale warning |
| `.agent.md` files load in VS Code | Agent selector shows config/triage/intel/ops agents |
| `.prompt.md` files are invocable | Prompt picker shows all 6 prompt files |
| `AGENTS.md` + `SKILL.md` files exist | All framework layers populated |
| `copilot-instructions.md` is prescriptive | Rules-based, not descriptive |

---

## Dependencies & Prerequisites

| Prerequisite | Verification |
|---|---|
| Phase 5 complete | 655 tests passing, tblTemplateStaging integration verified |
| Triage cross-reference gaps complete | `verify()` with DID matching, log/staging cross-ref working |
| Python 3.13.5 + `.venv` activated | `python --version` |
| SQLite available (stdlib) | Python stdlib — no install needed |
| VS Code with GitHub Copilot Chat | Required for testing `.agent.md` and `.prompt.md` |

---

## Why Not a Rewrite

The multi-agent framework defines **declarative metadata files** that guide Copilot's behavior. These files don't replace Python classes or JavaScript handlers — they sit alongside them. A rewrite would produce ~90% identical code plus the framework files, taking 2–4 months versus 3–5 days for a retrofit, with significant regression risk and zero additional value.

| Approach | Effort | Risk | Outcome |
|---|---|---|---|
| **Retrofit (chosen)** | 3–5 days | Near zero | Framework-compliant + all existing code preserved |
| **Rewrite (rejected)** | 2–4 months | High | Same code + framework files, bugs re-introduced |

The framework is the **instrument panel**. The existing codebase is the **engine**. You don't rebuild an engine because you want better gauges.

---

## Estimated Effort

| Work Stream | Estimated Hours | New Files | Modified Files |
|---|---|---|---|
| WS-A: SQLite Cache | 6–8 hours | 2 (module + tests) | 2 (cli/main.py internals) |
| WS-B: Framework Retrofit | 6–8 hours | ~20 (all markdown) | 1 (copilot-instructions.md rewrite) |
| **Total** | **12–16 hours** | **~22 files** | **3 files** |

> **Note:** The `participant.js` split is deferred to an optional future phase. The framework files work without it.
