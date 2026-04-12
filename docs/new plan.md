## Plan: Deterministic Triage

Replace the current agent-loop-driven `/triage` flow with a deterministic command family that uses direct backend triage commands for primary email analysis and existing deterministic jobs/deals/logs/staging infrastructure for drill-down and evidence rendering. Keep freeform fallback only for prompts that do not match the deterministic triage grammar.

**Current behavior today**
1. `/triage` is registered as a slash command in `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\package.json` and routed through `handleSlashCommand('triage', ...)` in `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\chat\participant.js`.
2. Unlike `/deals`, `/logs`, `/staging`, and deterministic job commands, `/triage` has no deterministic parser/handler today. In `handleSlashCommand`, it always maps to the `email_triage` pipeline and enters `agentLoop(...)`.
3. The `email_triage` pipeline uses `EMAIL_TRIAGE_PLAYBOOK` plus `EMAIL_TRIAGE_TOOLS`. The LLM decides which tools to call, in what order, and when to stop, with `maxSteps: 8`.
4. The `triage_email` tool is not a true deterministic triage surface today. Its schema advertises `sender`, `subject`, `msgPath`, `body`, and `mode`, but `executePipelineTool()` only extracts a `.msg` path and always calls `triage_verify`. If there is no `.msg` path, it returns an error instead of routing to `triage_match`.
5. This means `.msg`-based triage is partially deterministic only after the LLM chooses the `triage_email` tool, while sender/subject triage is almost entirely agentic today.

**Steps**
1. Phase 1: Formalize deterministic triage grammar in `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\chat\participant.js`.
2. Add a `parseDeterministicTriagePrompt()` and `handleDeterministicTriageCommand()` pair, modeled after deterministic `/logs` and `/staging`.
3. Support explicit subcommands first: `verify <path.msg>`, `match sender:<...>; subject:<...>`, `new <path.msg>`, and `trace <path.msg>` or `trace sender:<...>; subject:<...>`.
4. Keep a narrow shorthand only where it is unambiguous: a lone `.msg` path can infer `verify`, and field-only triage clauses can infer `match` or `trace` depending on the chosen command shape. This step depends on final syntax choice and blocks later parser work.
5. Phase 2: Route deterministic triage to direct backend triage commands instead of the agent loop.
6. `verify` should call `triage_verify` directly through the extension backend bridge and render the parsed email, best match, candidate matches, DID coverage, log summary, and template status already returned by the backend.
7. `match` should call `triage_match` directly and accept deterministic metadata fields such as `sender`, `subject`, and optionally `body`. This fixes the current mismatch where the tool schema suggests metadata matching but runtime handling does not actually do it.
8. `new` should call `triage_new` directly and render template suggestions plus suggested config overrides.
9. `trace` should act as the enhanced deterministic triage path: first seed from `triage_verify` or `triage_match`, then enrich with direct deterministic lookups from existing command families. This depends on steps 6 through 8.
10. Phase 3: Reuse existing deterministic command logic for end-to-end evidence gathering instead of inventing new triage-only logic.
11. Reuse job lookup/detail patterns already present in deterministic job commands so triage can surface the matched job, ServicerID, scrubber, sender filters, and mailbox consistently.
12. Reuse deterministic `/deals` logic for servicer or DID coverage, preferably by calling the same backend commands used there (`deal_lookup` and, where helpful, `servicer_dossier`) instead of re-encoding mapping rules in triage.
13. Reuse deterministic `/logs` logic for email evidence. Prefer `log_linkage` and/or deterministic log search helpers over the looser `daily_summary` narrative path when the goal is to tie sender, subject, filename, job, DID, and staging evidence together.
14. Reuse deterministic `/staging` logic for execution proof. Prefer `staging_linkage`, `staging_search`, `status`, and `source`-style lookups to confirm the exact file, template, run state, duration, and DataSource linkage.
15. Factor shared render helpers where needed so triage can produce a single deterministic report without duplicating whole `/deals`, `/logs`, or `/staging` renderers. Parallel with step 13 and step 14 after the data contract is clear.
16. Phase 4: Build the deterministic triage report and follow-up actions.
17. Render a stable report structure: Email Metadata, Job Match, Deal Coverage, Log Evidence, Staging Evidence, Outcome, Next Actions.
18. Attach deterministic follow-up prompts back into existing commands, such as jobs detail, deals servicer/did, logs linkage/search, and staging detail/linkage/source, so triage becomes the top-level orchestrator and existing commands remain the drill-down tools.
19. Preserve freeform `/triage` fallback only for prompts that do not match the deterministic grammar. This keeps compatibility while making straightforward triage requests deterministic by default.
20. Phase 5: Tighten help text and tests.
21. Update `/triage` help text so it documents the deterministic forms first and clearly distinguishes `verify`, `match`, `new`, and `trace`.
22. Add or update unit tests around the triage parser, tool dispatch, and help text, plus golden tests that prove deterministic tool selection for `.msg` verification, metadata matching, and full trace flows.
23. Add manual verification scenarios for real operator prompts such as `@frp /triage "<full network drive email .msg path>"` and metadata-only prompts that should no longer enter the full agent loop.

**Deterministic trace pipeline**
1. Entry classification:
2. If prompt is a lone `.msg` path or `verify <path.msg>`, call `triage_verify` first.
3. If prompt is `match sender:<...>; subject:<...>` or equivalent metadata clauses, call `triage_match` first.
4. If prompt is `new <path.msg>`, call `triage_new` and stop unless the user explicitly asks for cross-layer evidence.
5. If prompt is `trace ...`, call `triage_verify` for `.msg` input or `triage_match` for metadata input, then continue with the enrichment steps below.
6. Job resolution:
7. If triage returns one best match, call deterministic job detail for that exact job name: equivalent slash form `/jobXMLEmail detail <job_name>` and backend `job_detail` with `jobName=<job_name>`.
8. If triage returns multiple plausible matches, first render candidates from triage output, then optionally call deterministic job list to widen context using sender or mailbox filters: equivalent slash forms `/jobXMLEmail list sender:<sender_or_domain>` and `/jobXMLEmail list mailbox:<mailbox>`.
9. If triage returns no match, stop the trace path and pivot to `triage_new`; do not run deals/logs/staging lookups that depend on a resolved job.
10. Deal coverage:
11. If resolved job detail contains `servicer_id`, call deterministic dossier first: equivalent slash form `/deals dossier <servicer_id>` and backend `servicer_dossier` with `query=<servicer_id>`.
12. If you need exact DID rows and linked jobs table semantics, also call deterministic deal lookup: equivalent slash form `/deals servicer:<servicer_id>` and backend `deal_lookup` with `query=<servicer_id>`, `lookupType=servicer`, and `filtersJson=[{"type":"servicer","value":"<servicer_id>"}]`.
13. If triage already returned `did_matches`, for each matched DID or ImportDID keyword add targeted deterministic deal lookups: equivalent slash forms `/deals did:<did>` or `/deals keyword:<import_did>`.
14. If the resolved job has no `servicer_id`, mark it as process-level or shelf-level and skip DID-dependent branching.
15. Log evidence:
16. Preferred primary log call is deterministic linkage because it already bridges logs to jobs, deals, and staging: equivalent slash form `/logs linkage <query>; days:<n>; sender:<sender>; subject:<subject>; filename:<attachment>` and backend `log_linkage` with `query=<best_text_anchor>`, optional `days/startDate/endDate`, `limit`, and `filters` built from any available `job`, `sender`, `mailbox`, `subject`, `filename`, and `template` values.
17. Choose the best linkage anchor in this order: exact attachment filename if present, else exact email subject, else matched job name, else matched scrubber/template.
18. If a DID was deterministically identified, add deterministic DID activity: equivalent slash form `/logs deal <did>; days:<n>` and backend `log_deal_activity` with `did=<did>`.
19. If the resolved job name is known, add deterministic job health: equivalent slash form `/logs health <job_name>; days:<n>` and backend `log_job_health` with `jobName=<job_name>`.
20. If logs suggest DID-match problems or no DID was found despite a mapped servicer, add deterministic failures: equivalent slash form `/logs failures job:<job_name>; days:<n>` and backend `log_did_failures` with `jobFilter=<job_name>` when available.
21. Staging evidence:
22. Preferred primary staging call is deterministic linkage because it already bridges staging rows to jobs and deals: equivalent slash form `/staging linkage <query>; days:<n>` and backend `staging_linkage` with `query=<best_staging_anchor>`, `days=<n>`, `limit=<n>`.
23. Choose the best staging anchor in this order: exact attachment filename or filepath clue, else matched DID, else matched scrubber/template, else resolved servicer ID.
24. Add direct staging search when exact filters are stronger than a single text query: equivalent slash forms `/staging list filepath:<filename>; days:<n>`, `/staging list did:<did>; days:<n>`, `/staging list template:<scrubber>; days:<n>`, or `/staging list servicer:<servicer_id>; days:<n>` and backend `staging_search` with `query`, JSON `filters`, and optional `days/startDate/endDate`.
25. If a specific row is found, expose deterministic row drill-down: equivalent slash form `/staging detail <TemplateProcessID>`.
26. If the main question is whether the template is generally running, add deterministic status: equivalent slash form `/staging status <scrubber>` and backend `staging_search` seeded with the scrubber and a default recent window.
27. Final report assembly:
- User's expert triage heuristic is: parse sender/mailbox/subject/filenames first; use deterministic job search to narrow candidate jobs; use ServicerID to pull deal keywords; use parser match mode to decide subject-vs-filename DID matching; then query logs and staging in parallel, treating DataSource as the strongest proof for email-triggered staging.
- Recommended efficiency adjustment: after candidate jobs are narrowed, prefer exact `job_detail` for the top candidate(s) and dedupe ServicerIDs before deal lookups; prefer `log_linkage` and `staging_linkage` as primary evidence collectors, with filtered search/status as confirmatory calls.

**Implementation-grade decision mapping notes**
1. Deterministic job list is a two-step pattern today: backend `search_jobs(query)` returns broad candidates, then extension-side field filters narrow by `mailbox`, `sender`, `servicer_id`, `scrubber`, and related fields.
2. Deterministic `/deals` uses backend `deal_lookup` for exact row lookups and `servicer_dossier` for broad servicer context.
3. Deterministic `/logs linkage` is the preferred cross-layer log command because it already returns linked jobs, linked deals, and recent staging rows in one payload.
4. Deterministic `/staging linkage` is the preferred cross-layer staging command because it already returns linked jobs, linked deals, and missing-template context in one payload.
5. Parser match mode is authoritative for DID keyword matching: `Subject` means subject-only, `Filename` means attachment filename, `Both` means both.

**Status**
- Approved by user on 2026-03-12 for implementation handoff.
- First implementation target: deterministic `/triage trace` parser and dispatcher.
- Second target: direct orchestration of `triage_verify` / `triage_match` plus deterministic jobs/deals/logs/staging backend calls.
- Third target: deterministic triage report rendering and regression tests.


28. If triage found no job, return Email Metadata plus New Job Recommendation only.
29. If triage found a job but no deals, return Job Match plus Process-Level note plus Logs and Staging sections.
30. If triage found a job and deals but no DID keyword match, return Deal Coverage plus No Keyword Match plus any Logs/Staging evidence, and mark the DID branch as unresolved rather than failed.
31. If logs and staging both confirm the same file or subject, mark the email as processed with high confidence.
32. If logs confirm reception but staging is absent, mark as seen but not proven processed.
33. If staging confirms a matching DataSource or filepath but logs are weak, mark as processed with partial log evidence.
34. If neither logs nor staging confirm the email, mark as configured but unproven.
35. Always end with deterministic follow-up prompts into the existing command families: job detail, deals dossier or DID lookup, logs linkage or health, and staging detail or source.


**Relevant files**
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\chat\participant.js` — current slash routing, triage playbook/tools, special triage tool handling, deterministic command patterns to copy, help text, renderers, follow-up prompt helpers.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\package.json` — slash command registration and configuration surface.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\cli\main.py` — direct backend commands `triage_verify`, `triage_match`, `triage_new`, plus reusable jobs/deals/logs/staging command handlers.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\backend\triage\analyzer.py` — current backend triage data contract and what `verify`, `match_only`, and `analyze_new` actually return.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\backend\triage\matcher.py` — sender/subject matching semantics that deterministic `match` should expose clearly.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\backend\triage\msg_parser.py` — `.msg` parsing constraints and failure modes.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\test\unit\test_tool_schemas.js` — tool-schema and pipeline-related tests that will need updates for the new deterministic surface.
- `c:\Users\Karmsud\Projects\Prod Projects\FRP_Agent\extension\test\golden_test_cases.json` — expected-tool and behavior regression coverage for triage prompts.

**Verification**
1. Unit-test the triage prompt parser for valid and invalid deterministic forms, including `.msg` shorthand, field-only metadata clauses, and ambiguous prompts.
2. Verify deterministic dispatch with targeted extension tests: `verify <path.msg>` must call `triage_verify`, `match sender:...; subject:...` must call `triage_match`, `new <path.msg>` must call `triage_new`, and `trace ...` must stay entirely off the generic `agentLoop` path.
3. Verify deterministic drill-down orchestration by checking the returned follow-up prompts and rendered sections for jobs, deals, logs, and staging.
4. Manually run representative prompts in VS Code chat and confirm straightforward triage requests no longer produce the long agentic reasoning loop.
5. Confirm freeform prompts that do not match deterministic grammar still fall back safely to the existing agentic triage pipeline.

**Decisions**
- Included scope: deterministic `.msg` verification, deterministic sender/subject matching, deterministic new-email analysis, and a deterministic end-to-end triage report that reuses existing jobs/deals/logs/staging command logic.
- Included UX direction: keep `/triage` as the main user-facing command, add explicit deterministic subcommands, and use existing deterministic commands as the drill-down surface.
- Excluded for the first pass: redesigning backend domain logic in `backend/triage/*` unless deterministic orchestration exposes a real data-contract gap.
- Excluded for the first pass: removing the current agentic playbook entirely. It should remain as fallback for unsupported or conversational triage prompts.

**Further Considerations**
1. `trace` should probably be the single “full picture” deterministic subcommand so `verify` can stay focused on backend triage output and avoid doing too much work implicitly.
2. The current `triage_email` tool schema and runtime behavior are inconsistent. If `/triage` becomes deterministic, consider either fixing that tool to truly support `match` semantics or retiring it from the agentic pipeline in favor of direct slash routing.
3. For exact email evidence, `log_linkage` plus `staging_linkage` may be a better deterministic backbone than the current `daily_summary`-style playbook steps because they already model cross-layer traceability.