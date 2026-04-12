<#
.SYNOPSIS
    FRP Agent - Full Build Pipeline.
    Creates a Python venv, installs dependencies, compiles the backend exe
    with PyInstaller, packages the VS Code extension as a VSIX, and can install it.

.DESCRIPTION
    Reproducible build framework:
      1. Creates / reuses a Python virtual environment (.venv)
      2. Installs all dependencies from requirements.txt into the venv
      3. Compiles cli/main.py into extension/bin/win-x64/frp-backend/ via PyInstaller
      4. Stamps the version into extension/package.json
      5. Packages the extension folder into dist/frp-agent-<version>.vsix
    6. Optionally installs the packaged extension into the local VS Code profile

    Run from the repository root:
      .\scripts\build.ps1                   # full build, default version 0.1.0
      .\scripts\build.ps1 -Version 1.2.3    # full build, custom version
    .\scripts\build.ps1 -Version 1.2.3 -Install
                              # full build + install into local VS Code
      .\scripts\build.ps1 -SkipBackend      # VSIX only (reuse existing exe)
      .\scripts\build.ps1 -BackendOnly      # exe only (no VSIX)
      .\scripts\build.ps1 -Clean            # wipe build artifacts first

.PARAMETER Version
    Semantic version string stamped into the VSIX (default: 0.1.0).
.PARAMETER SkipBackend
    Skip the PyInstaller compilation step (reuse existing exe).
.PARAMETER BackendOnly
    Compile the backend exe and stop - skip VSIX packaging.
.PARAMETER Clean
    Remove all build artifacts (build/, dist/, extension/bin/) before starting.
.PARAMETER NoPip
    Skip pip install - use when the venv is already up to date.
.PARAMETER Install
    Install the packaged VSIX into the local VS Code profile after packaging.
#>
[CmdletBinding()]
param(
    [string]$Version   = "0.1.0",
    [switch]$SkipBackend,
    [switch]$BackendOnly,
    [switch]$Clean,
    [switch]$NoPip,
    [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Install -and $BackendOnly) {
    throw "-Install cannot be used with -BackendOnly because no VSIX is produced."
}

# === Paths ================================================================
$Root         = Split-Path -Parent $PSScriptRoot          # repo root
$VenvDir      = Join-Path $Root ".venv"
$VenvPython   = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip      = Join-Path $VenvDir "Scripts\pip.exe"
$VenvPyInst   = Join-Path $VenvDir "Scripts\pyinstaller.exe"
$Requirements = Join-Path $Root "requirements.txt"
$SpecFile     = Join-Path $Root "packaging\frp_backend.spec"
$ExtDir       = Join-Path $Root "extension"
$BinDest      = Join-Path $ExtDir "bin\win-x64"
$DistDir      = Join-Path $Root "dist"
$PkgJson      = Join-Path $ExtDir "package.json"
$LicenseSrc   = Join-Path $Root "LICENSE.txt"
$LicenseDst   = Join-Path $ExtDir "LICENSE.txt"
$UserExtensionsDir = Join-Path $HOME ".vscode\extensions"

$PackageMeta = Get-Content $PkgJson -Raw | ConvertFrom-Json
$ExtensionId = "$($PackageMeta.publisher).$($PackageMeta.name)"

function Test-InstalledExtensionVersion {
    param(
        [string]$ExtensionsDir,
        [string]$ExtensionId,
        [string]$Version
    )

    $installedPkgJson = Join-Path $ExtensionsDir "$ExtensionId-$Version\package.json"
    if (-not (Test-Path $installedPkgJson)) {
        return $false
    }

    try {
        $installedMeta = Get-Content $installedPkgJson -Raw | ConvertFrom-Json
        return $installedMeta.version -eq $Version
    } catch {
        return $false
    }
}

function Resolve-VSCodeCli {
    $candidates = @(
        (Get-Command code -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path $env:LOCALAPPDATA "Programs\Microsoft VS Code\Code.exe"),
        (Join-Path $env:ProgramFiles "Microsoft VS Code\Code.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft VS Code\Code.exe")
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Install-ExtensionPayload {
    param(
        [string]$VsixPath,
        [string]$ExtensionsDir,
        [string]$ExtensionId,
        [string]$Version
    )

    $targetDir = Join-Path $ExtensionsDir "$ExtensionId-$Version"
    if (-not (Test-Path $ExtensionsDir)) {
        New-Item -ItemType Directory -Path $ExtensionsDir | Out-Null
    }
    if (Test-Path $targetDir) {
        Remove-Item $targetDir -Recurse -Force
    }

    # Extract VSIX (zip) to a temp directory, then move extension/ contents
    $tempDir = Join-Path $env:TEMP "frp-vsix-extract-$(Get-Random)"
    try {
        $zipPath = Join-Path $tempDir "payload.zip"
        New-Item -ItemType Directory -Path $tempDir | Out-Null
        Copy-Item $VsixPath $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force
        $extractedExtDir = Join-Path $tempDir "extension"
        if (-not (Test-Path $extractedExtDir)) {
            throw "VSIX archive does not contain an 'extension/' directory."
        }
        # Move the extension/ contents (the actual extension files) to the target
        Move-Item $extractedExtDir $targetDir
        # Copy .vsixmanifest to target (VS Code expects it)
        $vsixManifest = Join-Path $tempDir ".vsixmanifest"
        if (Test-Path $vsixManifest) {
            Copy-Item $vsixManifest $targetDir
        }
    } finally {
        if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
    }

    # Stamp __metadata into installed package.json (VS Code expects this)
    $installedPkgJson = Join-Path $targetDir "package.json"
    $pkgData = Get-Content $installedPkgJson -Raw | ConvertFrom-Json
    $pkgData | Add-Member -NotePropertyName '__metadata' -NotePropertyValue @{
        installedTimestamp = [long](Get-Date -UFormat %s) * 1000
        targetPlatform    = "undefined"
    } -Force
    $pkgData | ConvertTo-Json -Depth 10 | Set-Content $installedPkgJson -Encoding UTF8

    # Register in extensions.json
    $extensionsJsonPath = Join-Path $ExtensionsDir "extensions.json"
    $entries = @()
    $payload = $null
    $wrapper = $null
    if (Test-Path $extensionsJsonPath) {
        $payload = @(Get-Content $extensionsJsonPath -Raw | ConvertFrom-Json)
        if ($payload.Count -eq 1 -and $payload[0].PSObject.Properties.Name -contains 'value') {
            $wrapper = $payload[0]
            $entries = @($wrapper.value)
        } else {
            $entries = @($payload)
        }
    }
    # Remove any existing entry for this extension
    $entries = @(
        $entries | Where-Object {
            -not ($_.PSObject.Properties.Name -contains 'identifier' -and $_.identifier -and $_.identifier.id -eq $ExtensionId)
        }
    )
    # Add the new entry
    $newEntry = [PSCustomObject]@{
        identifier       = [PSCustomObject]@{ id = $ExtensionId }
        version          = $Version
        location         = [PSCustomObject]@{
            '$mid'    = 1
            fsPath    = $targetDir
            path      = "/" + ($targetDir -replace '\\','/' -replace '^([A-Za-z]):', { $_.Groups[1].Value.ToLower() + ':' })
            scheme    = "file"
        }
        relativeLocation = "$ExtensionId-$Version"
        metadata         = [PSCustomObject]@{
            installedTimestamp = [long](Get-Date -UFormat %s) * 1000
            pinned            = $true
            source            = "vsix"
        }
    }
    $entries += $newEntry
    if ($wrapper) {
        $wrapper.value = @($entries)
        $payload = @($wrapper)
    } else {
        $payload = @($entries)
    }
    ConvertTo-Json $payload -Depth 10 | Set-Content $extensionsJsonPath -Encoding UTF8
}

# === Banner ===============================================================
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  FRP Agent Build Pipeline  v$Version" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Root      : $Root"
Write-Host "  Venv      : $VenvDir"
Write-Host "  Spec      : $SpecFile"
Write-Host "  Dist      : $DistDir"
Write-Host "  Ext ID    : $ExtensionId"
Write-Host ""

# === Step 0: Clean ========================================================
if ($Clean) {
    Write-Host "[CLEAN] Removing build artifacts..." -ForegroundColor Yellow
    foreach ($d in @("$Root\build", $DistDir, "$ExtDir\bin")) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    }
    Write-Host "[CLEAN] Done." -ForegroundColor Green
    Write-Host ""
}

# === Step 1: Virtual Environment ==========================================
Write-Host "[VENV] Ensuring virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path $VenvPython)) {
    Write-Host "       Creating .venv ..." -ForegroundColor DarkGray
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment." }
    Write-Host "       .venv created." -ForegroundColor Green
} else {
    Write-Host "       .venv already exists, reusing." -ForegroundColor DarkGray
}

# === Step 2: Install Dependencies =========================================
if (-not $NoPip) {
    Write-Host "[PIP]  Installing dependencies from requirements.txt..." -ForegroundColor Cyan
    # Upgrade pip (stderr output is normal here, so redirect)
    $ErrorActionPreference = 'Continue'
    & $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
    & $VenvPip install -r $Requirements --quiet 2>&1 | ForEach-Object { $_.ToString() } | Where-Object { $_ -notmatch '^\s*$' }
    $ErrorActionPreference = 'Stop'
    if (-not (Test-Path $VenvPyInst)) {
        throw "pip install succeeded but pyinstaller not found. Check requirements.txt."
    }
    Write-Host "[PIP]  Dependencies installed." -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "[PIP]  Skipping pip install (NoPip flag set)." -ForegroundColor Yellow
    Write-Host ""
}

# === Step 3: Compile Backend ==============================================
if (-not $SkipBackend) {
    Write-Host "[EXE]  Compiling Python backend with PyInstaller..." -ForegroundColor Cyan

    if (-not (Test-Path $VenvPyInst)) {
        throw "pyinstaller not found in .venv. Run without -NoPip first."
    }

    & $VenvPyInst $SpecFile --distpath $BinDest --workpath "$Root\build" --clean -y
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller compilation failed." }

    # Smoke test: verify the exe exists
    $ExePath = Join-Path $BinDest "frp-backend\frp-backend.exe"
    if (-not (Test-Path $ExePath)) {
        throw "Expected exe not found at $ExePath"
    }
    $sizeBytes = (Get-Item $ExePath).Length
    $sizeMB    = [math]::Round($sizeBytes / 1048576, 1)
    Write-Host "       frp-backend.exe  ($sizeMB MB)" -ForegroundColor DarkGray
    Write-Host "[EXE]  Backend compiled successfully." -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "[EXE]  Skipping backend compilation (SkipBackend flag set)." -ForegroundColor Yellow
    Write-Host ""
}

if ($BackendOnly) {
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "  BACKEND BUILD COMPLETE  (BackendOnly)" -ForegroundColor Green
    Write-Host "  Exe at: $BinDest\frp-backend\frp-backend.exe" -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""
    exit 0
}

# === Step 4: Stamp Version ================================================
Write-Host "[VER]  Setting version to $Version..." -ForegroundColor Cyan
$stampScript = @"
import json, pathlib
p = pathlib.Path(r'$PkgJson')
d = json.loads(p.read_text('utf-8'))
d['version'] = '$Version'
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n', 'utf-8', newline='\n')
"@
& $VenvPython -c $stampScript
if ($LASTEXITCODE -ne 0) { throw "Version stamp failed." }
Write-Host "[VER]  Done." -ForegroundColor Green
Write-Host ""

$SameVersionInstalled = Test-InstalledExtensionVersion -ExtensionsDir $UserExtensionsDir -ExtensionId $ExtensionId -Version $Version
if ($SameVersionInstalled) {
    Write-Warning "Extension version $Version is already installed in $UserExtensionsDir. Rebuilding the same version can leave VS Code using stale files. Prefer bumping -Version, or use -Install to refresh the local extension."
    Write-Host ""
}

# === Step 5: Copy LICENSE into extension ==================================
Write-Host "[LIC]  Copying LICENSE.txt into extension/..." -ForegroundColor Cyan
if (Test-Path $LicenseSrc) {
    Copy-Item $LicenseSrc $LicenseDst -Force
    Write-Host "[LIC]  Done." -ForegroundColor Green
} else {
    Write-Host "[LIC]  WARNING: LICENSE.txt not found at repo root." -ForegroundColor Yellow
}
Write-Host ""

# === Step 6: Ensure dist/ =================================================
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}

# === Step 6b: Syntax-check extension JS ===================================
Write-Host "[LINT] Checking extension JavaScript for syntax errors..." -ForegroundColor Cyan
$jsFiles = Get-ChildItem $ExtDir -Filter "*.js" -Recurse | Where-Object { $_.FullName -notmatch '(node_modules|\.vscode-test|test)' }
$syntaxErrors = @()
foreach ($jsFile in $jsFiles) {
    & node --check $jsFile.FullName 2>&1 | ForEach-Object {
        $syntaxErrors += "$($jsFile.Name): $_"
    }
}
if ($syntaxErrors.Count -gt 0) {
    Write-Host "[LINT] Syntax errors found:" -ForegroundColor Red
    $syntaxErrors | ForEach-Object { Write-Host "       $_" -ForegroundColor Red }
    throw "Extension JavaScript has syntax errors. Fix them before packaging."
}
Write-Host "[LINT] All JS files OK." -ForegroundColor Green
Write-Host ""

# === Step 7: Verify vsce is available =====================================
Write-Host "[VSIX] Checking for @vscode/vsce..." -ForegroundColor Cyan
& npx @vscode/vsce --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "       Installing @vscode/vsce..." -ForegroundColor DarkGray
    & npm install -g @vscode/vsce
    if ($LASTEXITCODE -ne 0) { throw "Failed to install @vscode/vsce." }
}
Write-Host "[VSIX] vsce ready." -ForegroundColor Green
Write-Host ""

# === Step 8: Package VSIX =================================================
$VsixName = "frp-agent-$Version.vsix"
$VsixPath = Join-Path $DistDir $VsixName

Write-Host "[VSIX] Packaging extension..." -ForegroundColor Cyan
Push-Location $ExtDir
try {
    & npx @vscode/vsce package --no-dependencies --allow-missing-repository -o $VsixPath
    if ($LASTEXITCODE -ne 0) { throw "VSIX packaging failed." }
} finally {
    Pop-Location
}

$vsixSizeBytes = (Get-Item $VsixPath).Length
$vsixSizeMB    = [math]::Round($vsixSizeBytes / 1048576, 1)
Write-Host "[VSIX] $VsixName  ($vsixSizeMB MB)" -ForegroundColor DarkGray
Write-Host ""

# === Step 9: Optional install =============================================
if ($Install) {
    Write-Host "[INST] Installing extension..." -ForegroundColor Cyan
    $codeCli = Resolve-VSCodeCli

    if ($codeCli) {
        & $codeCli --install-extension $VsixPath --force
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "VS Code CLI install returned exit code $LASTEXITCODE. Falling back to direct local extension copy."
        }
    } else {
        Write-Warning "VS Code CLI not found. Falling back to direct local extension copy."
    }

    if ($SameVersionInstalled -or -not (Test-InstalledExtensionVersion -ExtensionsDir $UserExtensionsDir -ExtensionId $ExtensionId -Version $Version)) {
        Write-Host "[INST] Refreshing local extension files in $UserExtensionsDir..." -ForegroundColor Yellow
        Install-ExtensionPayload -VsixPath $VsixPath -ExtensionsDir $UserExtensionsDir -ExtensionId $ExtensionId -Version $Version
    }

    if (-not (Test-InstalledExtensionVersion -ExtensionsDir $UserExtensionsDir -ExtensionId $ExtensionId -Version $Version)) {
        throw "Extension install verification failed for $ExtensionId v$Version."
    }

    Write-Host "[INST] Installed $ExtensionId v$Version" -ForegroundColor Green
    Write-Host "       Reload VS Code to activate the updated extension." -ForegroundColor DarkGray
    Write-Host ""
}

# === Done =================================================================
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "  Backend : $BinDest\frp-backend\frp-backend.exe" -ForegroundColor Green
Write-Host "  VSIX    : $VsixPath" -ForegroundColor Green
if ($Install) {
    Write-Host "  Install : $UserExtensionsDir\$ExtensionId-$Version" -ForegroundColor Green
}
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
