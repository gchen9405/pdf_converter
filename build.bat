@echo off
setlocal enableextensions
REM ============================================================
REM  build.bat -- one-shot builder for the Docling PDF -> TXT exe
REM
REM  Usage:
REM     build.bat                 (digital PDFs; smaller, ~2-2.8 GB)
REM     build.bat --with-ocr      (also handles scanned PDFs; larger)
REM
REM  Requires Python 3.10, 3.11 or 3.12 installed (3.12 recommended; it is the
REM  validated version). Get it from https://www.python.org/downloads/ and tick
REM  "Add python.exe to PATH". Everything else is downloaded and installed into
REM  an isolated build venv automatically.
REM ============================================================

REM --- build / runtime env workarounds ------------------------
set "KMP_DUPLICATE_LIB_OK=TRUE"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

REM --- pick a SHORT build root to dodge the 260-char path limit
set "BUILD_ROOT=C:\pdfc"
mkdir "%BUILD_ROOT%" >nul 2>&1
if not exist "%BUILD_ROOT%\" set "BUILD_ROOT=%USERPROFILE%\pdfc"
mkdir "%BUILD_ROOT%" >nul 2>&1
set "TMP=%BUILD_ROOT%\t"
set "TEMP=%BUILD_ROOT%\t"
mkdir "%TMP%" >nul 2>&1

REM --- locate Python 3.10-3.12 (prefer 3.12, the validated version) -------
set "PYEXE="
for %%V in (3.12 3.11 3.10) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PYEXE=py -%%V"
    )
)
if not defined PYEXE (
    python -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info[:2]<(3,13) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
    echo.
    echo [ERROR] Python 3.10, 3.11 or 3.12 was not found.
    echo         Install it from https://www.python.org/downloads/
    echo         ^(tick "Add python.exe to PATH"^), then run this again.
    echo         Currently installed versions:
    py --list 2>nul
    goto :fail
)
echo [OK] Using interpreter: %PYEXE%
echo [OK] Build root: %BUILD_ROOT%
echo.

REM --- run the cross-platform builder (forwards --with-ocr etc.)
%PYEXE% "%~dp0build.py" --build-root "%BUILD_ROOT%" %*
if errorlevel 1 goto :fail

echo.
echo Done. The application folder path is printed above.
pause
exit /b 0

:fail
echo.
echo *** BUILD FAILED -- read the messages above. ***
pause
exit /b 1
