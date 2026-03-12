@echo off
setlocal EnableDelayedExpansion
title yt-dlp GUI Launcher
cd /d "%~dp0"

echo.
echo  +------------------------------------------+
echo  ^|           yt-dlp GUI  Launcher           ^|
echo  +------------------------------------------+
echo.

set "GUI_PY=%~dp0gui.py"
set "EMBED_DIR=%~dp0python_embedded"
set "PBS_TAG=20250702"
set "PBS_VER=3.13.5"
set "GOOD_PY="

REM ── Detect architecture ───────────────────────────────────────────────────────
set "WIN_ARCH=x86_64-pc-windows-msvc"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64"  set "WIN_ARCH=aarch64-pc-windows-msvc"
if /I "%PROCESSOR_ARCHITEW6432%"=="ARM64"  set "WIN_ARCH=aarch64-pc-windows-msvc"

set "PBS_FILE=cpython-%PBS_VER%+%PBS_TAG%-%WIN_ARCH%-install_only.tar.gz"
set "PBS_URL=https://github.com/indygreg/python-build-standalone/releases/download/%PBS_TAG%/%PBS_FILE%"
set "TMP_TGZ=%TEMP%\ytdlpgui_python.tar.gz"
set "TMP_TAR=%TEMP%\ytdlpgui_python.tar"

REM ── Helper: find python.exe anywhere under EMBED_DIR ─────────────────────────
REM Sets EMBED_EXE to the first python.exe found, or leaves it empty
call :find_python_exe
if defined EMBED_EXE (
    "%EMBED_EXE%" -c "import sys,tkinter; assert sys.version_info>=(3,8)" >nul 2>&1
    if !errorlevel! == 0 (
        echo  [Launcher] Embedded Python OK: !EMBED_EXE!
        set "GOOD_PY=!EMBED_EXE!"
        goto :run_gui
    )
    echo  [Launcher] Embedded Python check failed - re-downloading.
    rmdir /s /q "%EMBED_DIR%" >nul 2>&1
    set "EMBED_EXE="
)

REM ── 2. System Python with tkinter? ───────────────────────────────────────────
echo  [Launcher] Checking for system Python...
for %%C in (python3 python py) do (
    if not defined GOOD_PY (
        %%C --version >nul 2>&1
        if !errorlevel! == 0 (
            %%C -c "import sys,tkinter; assert sys.version_info>=(3,8)" >nul 2>&1
            if !errorlevel! == 0 (
                for /f "delims=" %%P in ('where %%C 2^>nul') do (
                    if not defined GOOD_PY set "GOOD_PY=%%P"
                )
                echo  [Launcher] System Python found: !GOOD_PY!
            )
        )
    )
)
if defined GOOD_PY goto :run_gui

REM ── 3. Download python-build-standalone ──────────────────────────────────────
echo  [Launcher] No system Python found. Downloading standalone Python...
echo  [Launcher] This only happens once (~25 MB).
echo.

if not exist "%EMBED_DIR%" mkdir "%EMBED_DIR%"
set "DL_OK=0"

REM ── Method A: curl.exe
echo  [Launcher] Trying curl.exe...
where curl.exe >nul 2>&1
if %errorlevel% == 0 (
    curl.exe -L --progress-bar --output "%TMP_TGZ%" "%PBS_URL%" 2>&1
    if !errorlevel! == 0 if exist "%TMP_TGZ%" (
        echo  [Launcher] curl.exe succeeded.
        set "DL_OK=1"
    ) else (
        echo  [Launcher] curl.exe failed.
        if exist "%TMP_TGZ%" del /f "%TMP_TGZ%" >nul 2>&1
    )
) else (
    echo  [Launcher] curl.exe not available.
)

REM ── Method B: PowerShell Invoke-WebRequest
if %DL_OK% == 0 (
    echo  [Launcher] Trying PowerShell Invoke-WebRequest...
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
      "$ProgressPreference = 'SilentlyContinue'; " ^
      "Invoke-WebRequest -Uri '%PBS_URL%' -OutFile '%TMP_TGZ%' -UseBasicParsing"
    if !errorlevel! == 0 if exist "%TMP_TGZ%" (
        echo  [Launcher] Invoke-WebRequest succeeded.
        set "DL_OK=1"
    ) else (
        echo  [Launcher] Invoke-WebRequest failed.
        if exist "%TMP_TGZ%" del /f "%TMP_TGZ%" >nul 2>&1
    )
)

REM ── Method C: PowerShell WebClient
if %DL_OK% == 0 (
    echo  [Launcher] Trying PowerShell WebClient...
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
      "$wc = New-Object Net.WebClient; " ^
      "$wc.Headers.Add('User-Agent','yt-dlp-gui/1.0'); " ^
      "$wc.DownloadFile('%PBS_URL%','%TMP_TGZ%')"
    if !errorlevel! == 0 if exist "%TMP_TGZ%" (
        echo  [Launcher] WebClient succeeded.
        set "DL_OK=1"
    ) else (
        echo  [Launcher] WebClient failed.
        if exist "%TMP_TGZ%" del /f "%TMP_TGZ%" >nul 2>&1
    )
)

if %DL_OK% == 0 (
    echo.
    echo  [ERROR] All download methods failed.
    echo  Download the file manually and save it to: %TMP_TGZ%
    echo  Then re-run launch.bat.
    echo  URL: %PBS_URL%
    pause
    exit /b 1
)

REM ── Extract ───────────────────────────────────────────────────────────────────
echo  [Launcher] Extracting Python (this may take 30-60 seconds)...

REM Decompress .gz -> .tar via PowerShell .NET, then extract .tar via tar.exe
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "try { " ^
  "  $in  = [IO.File]::OpenRead('%TMP_TGZ%'); " ^
  "  $gz  = New-Object IO.Compression.GZipStream($in,[IO.Compression.CompressionMode]::Decompress); " ^
  "  $out = [IO.File]::Create('%TMP_TAR%'); " ^
  "  $gz.CopyTo($out); " ^
  "  $out.Close(); $gz.Close(); $in.Close(); " ^
  "  Write-Host '  Decompressed OK.' " ^
  "} catch { Write-Host ('  GZ_ERROR: '+$_); exit 1 }"

if %errorlevel% neq 0 (
    echo  [ERROR] Decompression failed.
    if exist "%TMP_TGZ%" del /f "%TMP_TGZ%" >nul 2>&1
    pause
    exit /b 1
)
if exist "%TMP_TGZ%" del /f "%TMP_TGZ%" >nul 2>&1

echo  [Launcher] Running tar extraction...
tar -xf "%TMP_TAR%" -C "%EMBED_DIR%"
if %errorlevel% neq 0 (
    echo  [ERROR] tar extraction failed.
    if exist "%TMP_TAR%" del /f "%TMP_TAR%" >nul 2>&1
    pause
    exit /b 1
)
if exist "%TMP_TAR%" del /f "%TMP_TAR%" >nul 2>&1

REM ── Find python.exe wherever it landed ───────────────────────────────────────
echo  [Launcher] Locating python.exe...
call :find_python_exe
if not defined EMBED_EXE (
    echo  [ERROR] python.exe not found anywhere under:
    echo    %EMBED_DIR%
    echo.
    echo  Folder contents:
    dir "%EMBED_DIR%" /b /s 2>nul
    pause
    exit /b 1
)
echo  [Launcher] Found: %EMBED_EXE%

REM ── Verify ────────────────────────────────────────────────────────────────────
echo  [Launcher] Verifying Python + tkinter...
"%EMBED_EXE%" -c "import sys,tkinter; print('  Python', sys.version[:6], '+ tkinter OK')"
if %errorlevel% neq 0 (
    echo  [ERROR] tkinter verification failed.
    pause
    exit /b 1
)

REM ── Save the located path so future launches skip all of the above ─────────────
echo %EMBED_EXE%> "%EMBED_DIR%\python_exe.txt"
set "GOOD_PY=%EMBED_EXE%"
goto :run_gui

REM ── Launch ────────────────────────────────────────────────────────────────────
:run_gui
if not defined GOOD_PY set "GOOD_PY=%EMBED_EXE%"
title yt-dlp GUI
echo  [Launcher] Starting GUI...
echo.
"%GOOD_PY%" "%GUI_PY%"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Application exited with error %errorlevel%
    pause
)
endlocal
goto :eof

REM ── Subroutine: find python.exe under EMBED_DIR ───────────────────────────────
:find_python_exe
set "EMBED_EXE="
REM Check cached path from previous run first
if exist "%EMBED_DIR%\python_exe.txt" (
    set /p EMBED_EXE=<"%EMBED_DIR%\python_exe.txt"
    if defined EMBED_EXE if exist "!EMBED_EXE!" goto :eof
    set "EMBED_EXE="
)
REM Search common PBS layout paths
for %%P in (
    "%EMBED_DIR%\python\python.exe"
    "%EMBED_DIR%\python.exe"
    "%EMBED_DIR%\python\bin\python.exe"
    "%EMBED_DIR%\Python\python.exe"
    "%EMBED_DIR%\Python313\python.exe"
    "%EMBED_DIR%\Python312\python.exe"
) do (
    if not defined EMBED_EXE (
        if exist %%P set "EMBED_EXE=%%~P"
    )
)
REM Last resort: recursive search
if not defined EMBED_EXE (
    for /f "delims=" %%F in ('dir "%EMBED_DIR%\python.exe" /s /b 2^>nul') do (
        if not defined EMBED_EXE set "EMBED_EXE=%%F"
    )
)
goto :eof
