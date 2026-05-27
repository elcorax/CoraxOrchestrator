@echo off
REM ============================================================================
REM Corax Orchestrator - Windows Build Script (Batch)
REM ============================================================================
REM Builds Corax into a standalone Windows executable using PyInstaller.
REM
REM Usage:
REM   build_windows.bat              - Full build
REM   build_windows.bat clean        - Clean build
REM   build_windows.bat debug        - Debug build with console window
REM   build_windows.bat quick        - Skip tests and validation
REM ============================================================================

setlocal enabledelayedexpansion
set PROJECT_DIR=%~dp0
set BUILD_LOG=%PROJECT_DIR%build_corax.log

echo [%DATE% %TIME%] === Corax Orchestrator Build === > "%BUILD_LOG%"
echo [%DATE% %TIME%] Project Root: %PROJECT_DIR% >> "%BUILD_LOG%"

REM Parse arguments
set CLEAN_FLAG=
set DEBUG_FLAG=
set QUICK_FLAG=

:parse_args
if "%~1"=="clean" set CLEAN_FLAG=1
if "%~1"=="debug" set DEBUG_FLAG=1
if "%~1"=="quick" set QUICK_FLAG=1
shift
if not "%~1"=="" goto parse_args

REM Step 1: Check Python
echo [%DATE% %TIME%] Checking Python... >> "%BUILD_LOG%"
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+.
    echo [%DATE% %TIME%] [ERROR] Python not found >> "%BUILD_LOG%"
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo Python: %%i
echo [%DATE% %TIME%] Python found >> "%BUILD_LOG%"

REM Step 2: Install dependencies
if "%QUICK_FLAG%"=="" (
    echo Installing build dependencies...
    echo [%DATE% %TIME%] Installing dependencies... >> "%BUILD_LOG%"
    pip install --upgrade pip >> "%BUILD_LOG%" 2>&1
    pip install pyinstaller >> "%BUILD_LOG%" 2>&1
    pip install -r "%PROJECT_DIR%requirements.txt" >> "%BUILD_LOG%" 2>&1
)

REM Step 3: Validate environment
if "%QUICK_FLAG%"=="" (
    echo Validating environment...
    echo [%DATE% %TIME%] Validating environment... >> "%BUILD_LOG%"
    
    python -c "import PySide6" >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] PySide6 not installed!
        echo [%DATE% %TIME%] [ERROR] PySide6 not installed >> "%BUILD_LOG%"
        exit /b 1
    )
    
    echo Environment validation passed.
    echo [%DATE% %TIME%] Environment validation passed >> "%BUILD_LOG%"
)

REM Step 4: Quick syntax check
if "%QUICK_FLAG%"=="" (
    echo Running syntax check...
    echo [%DATE% %TIME%] Running syntax check... >> "%BUILD_LOG%"
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
" >> "%BUILD_LOG%" 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Syntax check failed!
        exit /b 1
    )
    echo Syntax check passed.
)

REM Step 5: Clean if requested
if "%CLEAN_FLAG%"=="1" (
    echo Cleaning previous builds...
    echo [%DATE% %TIME%] Cleaning builds... >> "%BUILD_LOG%"
    if exist "%PROJECT_DIR%build" rmdir /s /q "%PROJECT_DIR%build"
    if exist "%PROJECT_DIR%dist" rmdir /s /q "%PROJECT_DIR%dist"
)

REM Step 6: Ensure data directories
if not exist "%PROJECT_DIR%data\logs" mkdir "%PROJECT_DIR%data\logs"
if not exist "%PROJECT_DIR%data\reports" mkdir "%PROJECT_DIR%data\reports"
if not exist "%PROJECT_DIR%data\persistence" mkdir "%PROJECT_DIR%data\persistence"
if not exist "%PROJECT_DIR%data\models" mkdir "%PROJECT_DIR%data\models"

REM Step 7: Run PyInstaller
echo Building Corax executable...
echo [%DATE% %TIME%] Running PyInstaller... >> "%BUILD_LOG%"

cd /d "%PROJECT_DIR%"
if "%DEBUG_FLAG%"=="1" (
    set PYINSTALLER_DEBUG=1
)

pyinstaller --noconfirm corax.spec >> "%BUILD_LOG%" 2>&1
set BUILD_RESULT=%ERRORLEVEL%

if "%DEBUG_FLAG%"=="1" (
    set PYINSTALLER_DEBUG=
)

if %BUILD_RESULT% neq 0 (
    echo [ERROR] PyInstaller build failed! Check build_corax.log for details.
    echo [%DATE% %TIME%] [ERROR] PyInstaller build failed >> "%BUILD_LOG%"
    exit /b 1
)

REM Step 8: Verify build
if exist "%PROJECT_DIR%dist\corax.exe" (
    for %%i in ("%PROJECT_DIR%dist\corax.exe") do set EXE_SIZE=%%~zi
    set /a EXE_SIZE_MB=!EXE_SIZE! / 1048576
    echo Build successful: dist\corax.exe (!EXE_SIZE_MB! MB)
    echo [%DATE% %TIME%] Build successful: dist\corax.exe (!EXE_SIZE_MB! MB) >> "%BUILD_LOG%"
) else (
    echo [ERROR] Build output not found!
    echo [%DATE% %TIME%] [ERROR] Build output not found >> "%BUILD_LOG%"
    exit /b 1
)

REM Step 9: Copy config and data
if not exist "%PROJECT_DIR%dist\config" xcopy /E /I /Y "%PROJECT_DIR%config" "%PROJECT_DIR%dist\config" >nul
if not exist "%PROJECT_DIR%dist\data" xcopy /E /I /Y "%PROJECT_DIR%data" "%PROJECT_DIR%dist\data" >nul

REM Step 10: Create launcher
echo @echo off > "%PROJECT_DIR%dist\run_corax.bat"
echo REM Corax Orchestrator - Launcher >> "%PROJECT_DIR%dist\run_corax.bat"
echo cd /d "%%~dp0" >> "%PROJECT_DIR%dist\run_corax.bat"
echo start "" "%%~dp0corax.exe" >> "%PROJECT_DIR%dist\run_corax.bat"

echo.
echo === Build Complete ===
echo Output: %PROJECT_DIR%dist\
echo Executable: %PROJECT_DIR%dist\corax.exe
echo Build log: %BUILD_LOG%
echo [%DATE% %TIME%] === Build Complete === >> "%BUILD_LOG%"

endlocal
