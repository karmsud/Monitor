# packaging/frp_backend.spec
# ──────────────────────────────────────────────────────────────────
# PyInstaller spec for the FRP Agent Python backend.
#
# Invoked by scripts/build.ps1 — not intended for direct use.
#
# Manual usage (from repo root):
#   .venv\Scripts\pyinstaller packaging\frp_backend.spec `
#       --distpath extension\bin\win-x64 `
#       --workpath build --clean -y
# ──────────────────────────────────────────────────────────────────

import os

# SPECPATH is the directory containing this .spec file (set by PyInstaller).
# packaging/ is one level below the repo root.
REPO_ROOT = os.path.dirname(SPECPATH)

a = Analysis(
    [os.path.join(REPO_ROOT, 'cli', 'main.py')],
    pathex=[REPO_ROOT],
    datas=[
        (os.path.join(REPO_ROOT, 'config'), 'config'),
    ],
    hiddenimports=[
        # ── Phase 1: Foundation ──────────────────────────────────
        'backend.xml.parser',
        'backend.xml.writer',
        'backend.xml.models',
        'backend.db.connection',
        'backend.db.connection_mysql',
        'backend.db.connection_mssql',
        'backend.db.deal_repo',
        'backend.db.queries',
        'backend.logs.parser',
        'backend.logs.indexer',
        'backend.logs.models',
        'backend.backup.manager',
        'backend.common.models',
        'backend.common.config',
        'backend.common.errors',
        # ── Phase 2: CRUD & Intelligence ─────────────────────────
        'backend.xml.crud',
        'backend.xml.diff',
        'backend.xml.rollback',
        'backend.xml.templates',
        'backend.intel.coverage',
        'backend.intel.orphans',
        'backend.intel.collisions',
        'backend.intel.models',
        # ── Phase 3: Log Analytics & Email Triage ────────────────
        'backend.logs.analytics',
        'backend.triage.analyzer',
        'backend.triage.matcher',
        'backend.triage.msg_parser',
        'backend.triage.models',
        # ── Phase 4: Advanced Analysis ───────────────────────────
        'backend.analysis.consolidation',
        'backend.analysis.health',
        'backend.analysis.impact',
        'backend.analysis.performance',
        'backend.analysis.trends',
        'backend.analysis.models',
        # ── Phase 5: Template Staging ────────────────────────────
        'backend.db.template_staging_repo',
        'backend.db.ts_models',
        # ── Phase 6: SQLite XML Cache ────────────────────────────
        'backend.db.xml_index',
        # ── External dependencies ────────────────────────────────
        'pyodbc',
        'extract_msg',
    ],
    excludes=[
        # Test-only packages — keep the exe lean
        'pytest', 'pytest_cov', 'freezegun',
        'tkinter', 'unittest',
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='frp-backend',
    console=True,
    strip=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='frp-backend',
)
