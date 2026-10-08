@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Apex Patch Insight - RUNNING
color 0A

echo ==================================================
echo Apex Patch Insight
echo Visible foreground console - do not close while using the app.
echo Close this window to stop the application.
echo URL: http://127.0.0.1:8503
echo ==================================================
echo.

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [ERROR] Python was not found: %VENV_PY%
    echo The window will stay open so you can read this error.
    pause
    exit /b 1
)

echo Checking dependencies...
"%VENV_PY%" -c "import streamlit, pandas, openai, pydantic, rapidfuzz" >nul 2>nul
if errorlevel 1 (
    echo Installing missing dependencies...
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
)

:launch
echo.
echo [RUNNING] Starting Streamlit in this visible window...
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:8503/_stcore/health'; for($i=0;$i -lt 30;$i++){try{if((Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 1).Content -eq 'ok'){Start-Process 'http://127.0.0.1:8503'; exit}}catch{}; Start-Sleep -Seconds 1}"
"%VENV_PY%" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8503 --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false
set "APP_EXIT=%ERRORLEVEL%"

echo.
echo ==================================================
echo [STOPPED] Streamlit exited with code %APP_EXIT%.
echo This BAT window is intentionally staying open.
echo Press R to restart, or Q to close this window.
echo ==================================================
choice /C RQ /N /M "[R] Restart  [Q] Quit: "
if errorlevel 2 exit /b %APP_EXIT%
goto launch