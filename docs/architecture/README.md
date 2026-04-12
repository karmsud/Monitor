# FRP Architecture Diagrams

This folder contains the current clean technical architecture package and an archive for retired variants.

Files:

- `frp-architecture.drawio`: active diagrams.net source file for the clean technical set
- `svg/`: active SVG exports for the clean technical set
- `archived/frp-architecture-archive.drawio`: archived executive and style-variant pages
- `archived/svg/`: archived SVG exports for retired pages

Page set:

1. `Master - Technical`: one-page detailed architecture summary
2. `Context - Technical`: walkthrough page 1, detailed boundaries
3. `Request Flow - Technical`: walkthrough page 2, detailed control flow
4. `Data Lineage - Technical`: walkthrough page 3, detailed data lineage and mutation safety

Archived page set:

1. `Clean Enterprise`: retired style comparison page
2. `Visio Style`: retired style comparison page
3. `Modern Board`: retired style comparison page
4. `Master - Executive`: archived executive summary page
5. `Context - Executive`: archived executive walkthrough page
6. `Request Flow - Executive`: archived executive control-flow page
7. `Data Lineage - Executive`: archived executive data-lineage page

Regenerate the active and archived packages:

```powershell
python scripts/generate_architecture_drawio.py
```

Recommended review and export workflow:

1. Review the SVG assets under `docs/architecture/svg/`
2. Open `docs/architecture/frp-architecture.drawio`
3. Use the technical pages as the presentation baseline
4. Open `docs/architecture/archived/frp-architecture-archive.drawio` only if you need the retired executive or style-variant material
5. Export PNG copies from draw.io for PowerPoint or email distribution when raster output is needed

Recommended walkthrough order:

1. `Master - Technical`
2. `Context - Technical`
3. `Request Flow - Technical`
4. `Data Lineage - Technical`

Suggested Copilot prompts for future refinement:

- `Refine the technical request flow page to highlight deterministic slash commands and clone workflows.`
- `Add a deeper technical page for triage, log linkage, and staging linkage cross-references.`
- `Split the master technical page into separate extension, backend, and data architecture pages.`