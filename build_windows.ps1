#Requires -Version 5.1
<#
.SYNOPSIS
    Corax Orchestrator - Windows Build Script (PowerShell)
.DESCRIPTION
    Builds Corax into a standalone Windows executable using PyInstaller.
    Handles dependency installation, environment validation, and packaging.
#>

param(
    [switch]$Clean,
    [switch]$Debug,
    [switch]$SkipDeps,
    [switch]$SkipTests,
    [switch]$SkipValidation,
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot $OutputDir
$LogFile = Join-Path $ProjectRoot "build_corax.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] [$Level] $Message"
    Write-Host $logLine
    Add-Content -Path $LogFile -Value $logLine
}

function Test-Command {
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Initialize-BuildEnvironment {
    Write-Log "Initializing build environment..."

    # Check Python
    if (-not (Test-Command "python")) {
        Write-Log "Python not found!" "ERROR"
        return $false
    }

    $pythonVersion = python --version 2>&1
    Write-Log "Python: $pythonVersion"

    # Check pip
    if (-not (Test-Command "pip")) {
        Write-Log "pip not found!" "ERROR"
        return $false
    }

    # Install/upgrade build tools
    if (-not $SkipDeps) {
        Write-Log "Installing build dependencies..."
        pip install --upgrade pip 2>&1 | Out-Null
        pip install pyinstaller 2>&1 | Out-Null
        pip install -r "$ProjectRoot\requirements.txt" 2>&1 | Out-Null
    }

    return $true
}

function Test-Environment {
    Write-Log "Validating environment..."

    # Check PyInstaller
    if (-not (Test-Command "pyinstaller")) {
        Write-Log "PyInstaller not found!" "ERROR"
        return $false
    }

    # Check PySide6
    try {
        python -c "import PySide6; print(f'PySide6: {PySide6.__version__}')" 2>&1
    } catch {
        Write-Log "PySide6 not installed!" "ERROR"
        return $false
    }

    # Check core modules
    $modules = @(
        "yaml", "aiohttp", "aiofiles", "psutil", "requests", "packaging"
    )
    foreach ($mod in $modules) {
        try {
            python -c "import $mod" 2>&1 | Out-Null
        } catch {
            Write-Log "Missing dependency: $mod" "WARN"
        }
    }

    # Check source structure
    $requiredDirs = @(
        "src\gui\panels",
        "src\runtime",
        "src\deployment",
        "src\deployment\installers",
        "src\deployment\execution",
        "src\deployment\models",
        "src\deployment\profiles",
        "src\deployment\verification",
        "src\deployment\integration",
        "src\deployment\repair",
        "src\deployment\config",
        "src\modules",
        "src\platform",
        "src\utils",
        "src\health",
        "src\agent",
        "src\agent\runtime",
        "src\agent\modes",
        "src\agent\execution",
        "src\agent\execution\capabilities",
        "src\agent\reasoning",
        "src\agent\providers",
        "src\agent\conversation",
        "src\core",
        "config",
        "data"
    )

    foreach ($dir in $requiredDirs) {
        $fullPath = Join-Path $ProjectRoot $dir
        if (-not (Test-Path $fullPath)) {
            Write-Log "Missing directory: $dir" "ERROR"
            return $false
        }
    }

    Write-Log "Environment validation passed"
    return $true
}

function Invoke-Tests {
    param([switch]$Quick)
    Write-Log "Running tests..."

    if ($Quick) {
        # Quick syntax check
        python -c "
import ast, sys, os
errors = []
for root, dirs, files in os.walk('src'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    ast.parse(fh.read())
            except SyntaxError as e:
                errors.append(f'{path}: {e}')
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print('All Python files parse successfully')
" 2>&1
    } else {
        # Full test suite
        python -m pytest tests/ -v --tb=short 2>&1
    }

    Write-Log "Tests completed"
}

function Invoke-Build {
    param([switch]$DebugBuild)
    Write-Log "Starting PyInstaller build..."

    # Clean previous builds
    if ($Clean -and (Test-Path $BuildDir)) {
        Remove-Item -Recurse -Force $BuildDir
        Write-Log "Cleaned build directory"
    }
    if ($Clean -and (Test-Path $DistDir)) {
        Remove-Item -Recurse -Force $DistDir
        Write-Log "Cleaned dist directory"
    }

    # Ensure output directories exist
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "data\logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "data\reports") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "data\persistence") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "data\models") | Out-Null

    # Run PyInstaller
    $specFile = Join-Path $ProjectRoot "corax.spec"
    if ($DebugBuild) {
        $env:PYINSTALLER_DEBUG = "1"
    }

    Push-Location $ProjectRoot
    try {
        pyinstaller --noconfirm $specFile 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
        Remove-Item Env:\PYINSTALLER_DEBUG -ErrorAction SilentlyContinue
    }

    # Verify build output
    $exePath = Join-Path $DistDir "corax.exe"
    if (Test-Path $exePath) {
        $fileInfo = Get-Item $exePath
        Write-Log "Build successful: $exePath ($([math]::Round($fileInfo.Length / 1MB, 2)) MB)"
    } else {
        Write-Log "Build output not found: $exePath" "ERROR"
        return $false
    }

    # Copy config and data
    Copy-Item -Recurse -Force (Join-Path $ProjectRoot "config") (Join-Path $DistDir "config")
    Copy-Item -Recurse -Force (Join-Path $ProjectRoot "data") (Join-Path $DistDir "data")

    # Create startup script
    $startScript = @"
@echo off
REM Corax Orchestrator - Launcher
REM This script ensures proper working directory and launches Corax

cd /d "%~dp0"
start "" "%~dp0corax.exe"
"@
    Set-Content -Path (Join-Path $DistDir "run_corax.bat") -Value $startScript

    Write-Log "Build artifacts prepared in: $DistDir"
    return $true
}

function Invoke-SmokeTest {
    Write-Log "Running smoke tests..."

    $exePath = Join-Path $DistDir "corax.exe"
    if (-not (Test-Path $exePath)) {
        Write-Log "Executable not found for smoke test" "ERROR"
        return $false
    }

    # Run executable smoke test
    python "$ProjectRoot\tests\executable_smoke_test.py" 2>&1

    Write-Log "Smoke tests completed"
    return $true
}

# ─── Main Build Pipeline ────────────────────────────────────────────────

Write-Log "=== Corax Orchestrator Build ==="
Write-Log "Project Root: $ProjectRoot"
Write-Log "Build started at $(Get-Date)"

# Step 1: Initialize
if (-not (Initialize-BuildEnvironment)) {
    Write-Log "Build environment initialization failed!" "ERROR"
    exit 1
}

# Step 2: Validate
if (-not $SkipValidation) {
    if (-not (Test-Environment)) {
        Write-Log "Environment validation failed!" "ERROR"
        exit 1
    }
}

# Step 3: Tests
if (-not $SkipTests) {
    Invoke-Tests -Quick
}

# Step 4: Build
if (-not (Invoke-Build -DebugBuild:$Debug)) {
    Write-Log "Build failed!" "ERROR"
    exit 1
}

# Step 5: Smoke test
Invoke-SmokeTest

Write-Log "=== Build Complete ==="
Write-Log "Output: $DistDir"
Write-Log "Executable: $(Join-Path $DistDir 'corax.exe')"
Write-Log "Build log: $LogFile"
