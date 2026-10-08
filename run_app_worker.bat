@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Apex Patch Insight - STARTING
color 0F
echo ==================================================
echo   Apex Patch Insight
echo ==================================================
echo   This window owns the application process.
echo   Keep it open while using the app.
echo   Closing it or pressing Ctrl+C stops the app.
echo ==================================================
echo.

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [1/3] Creating virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 py -3.11 -m venv .venv
)

if not exist "%VENV_PY%" (
    where python >nul 2>nul
    if errorlevel 1 goto :already_running
title Apex Patch Insight - ALREADY RUNNING
color 0E
echo.
echo ==================================================
echo STATUS: ALREADY RUNNING
echo URL:    http://127.0.0.1:8501
echo Another process already owns the app service.
echo No second Streamlit process was started.
echo This command window will stay open.
echo ==================================================
start "" "http://127.0.0.1:8501"
goto :eof

:no_python
    python -m venv .venv
)

if not exist "%VENV_PY%" goto :venv_failed

echo [2/3] Checking dependencies...
"%VENV_PY%" -c "import streamlit, pandas, openai, pydantic, rapidfuzz, streamlit_paste_button" >nul 2>nul
if errorlevel 1 (
    echo Installing or repairing dependencies. Please wait...
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto :deps_failed
)

powershell.exe -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8501/_stcore/health' -TimeoutSec 2).Content -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 goto :already_running

echo [3/3] Starting local service...
echo.
echo --------------------------------------------------
echo STATUS: STARTING
echo URL:    http://127.0.0.1:8501
echo --------------------------------------------------
echo.

start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:8501/_stcore/health'; for($i=0;$i -lt 30;$i++){try{if((Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 1).Content -eq 'ok'){Start-Process 'http://127.0.0.1:8501'; exit}}catch{}; Start-Sleep -Seconds 1}"

title Apex Patch Insight - RUNNING - DO NOT CLOSE
color 0A
echo STATUS: RUNNING. Waiting for Streamlit output below...
echo.
"%VENV_PY%" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false
set "APP_EXIT=%ERRORLEVEL%"

title Apex Patch Insight - STOPPED
color 0C
echo.
echo ==================================================
echo STATUS: STOPPED
echo Exit code: %APP_EXIT%
if "%APP_EXIT%"=="0" (
    echo The application stopped normally.
) else (
    echo The application stopped because of an error.
    echo Read the Streamlit output above for details.
)
echo This window will remain open until you press a key.
echo ==================================================
pause
exit /b %APP_EXIT%

:already_running
title Apex Patch Insight - ALREADY RUNNING
color 0E
echo.
echo ==================================================
echo STATUS: ALREADY RUNNING
echo URL:    http://127.0.0.1:8501
echo Another process already owns the app service.
echo No second Streamlit process was started.
echo This command window will stay open.
echo ==================================================
start "" "http://127.0.0.1:8501"
goto :eof

:no_python
title Apex Patch Insight - PYTHON NOT FOUND
color 0C
echo ERROR: Python was not found. Install Python 3.11 and try again.
pause
exit /b 1

:venv_failed
title Apex Patch Insight - VENV FAILED
color 0C
echo ERROR: Virtual environment creation failed.
pause
exit /b 1

:deps_failed
title Apex Patch Insight - DEPENDENCY FAILED
color 0C
echo ERROR: Dependency installation failed. Check the messages above.
pause
exit /b 1
