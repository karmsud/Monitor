# FRP Agent Repository Instructions

## Domain model
- FRP manages monitoring jobs defined in email `Settings.xml` and optional SFTP `Settings.xml` files.
- Email jobs live under `Outlook/MailboxCollection`; SFTP jobs live under `Outlook/FolderCollection` or root-level `FolderCollection` depending on the file.
- `ServicerID` is treated as a unique operational identifier for deterministic lookup and cloning workflows.
- The SQLite cache mirrors XML jobs for fast search/detail lookups, but XML files remain the source of truth.

## Deterministic command rules
- Prefer deterministic slash-command flows when the task is narrow and well-scoped: `/jobs`, `/deals`, `/logs`, `/staging`, `/clone`, `/deploy`, `/rebuild-db`.
- Deterministic slash queries often accept semicolon-separated `AND` filters and should stay predictable rather than conversational.
- Automatic log sync is intentionally disabled. Users must refresh logs explicitly with `/sync_logs` or `/logs sync`.

## Clone workflow
- `/clone servicerID:<id>` must resolve the source job deterministically from `ServicerID`.
- New `ServicerID` selection must be the first unused integer upward from the source, considering configured email and SFTP XML files.
- Every leaf tag present on the source job is editable in source order, except `ServicerID`, which is auto-assigned and read-only.
- `JobName` is edited once and should stay synchronized with any optional `<Name>` child tag.
- Before writing the clone, always preview the exact XML block and require explicit confirmation.
- Writes must go through the existing XML writer so backup creation in the sibling `backup/` folder remains the single save path.

## XML mutation rules
- Do not bypass `backend/xml/writer.py` for final writes.
- Keep edits minimal and preserve existing XML structure/order unless the feature explicitly requires a structural change.
- After successful XML writes that affect jobs, rebuild the SQLite cache when a cache DB path is configured.

## Extension behavior
- The chat participant ID is `frp-agent.assistant`.
- Slash commands should stay thin and call stable backend commands rather than re-implementing business logic in JavaScript.
- Inline chat actions require trusted markdown and the `frp.runInlineChatAction` command.