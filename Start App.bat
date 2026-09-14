@echo off
title Onboarding Automation System
cd /d "%~dp0"

echo ============================================
echo   Onboarding Automation System - Starting
echo ============================================
echo.
echo   API       : http://localhost:8000
echo   Swagger   : http://localhost:8000/docs
echo   Frontend  : http://localhost:5173
echo.
echo   Leave this window open while you work.
echo   To stop everything, close this window or press Ctrl+C.
echo ============================================
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] backend\.venv not found. Run the one-time backend setup first
    echo         (see README.md "Getting started" -^> Backend^), then try again.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo [First run] Installing the launcher's own dependency...
    call npm install
)

if not exist "frontend\node_modules" (
    echo [First run] Installing frontend dependencies...
    call npm install --prefix frontend
)

REM Open the browser automatically once the frontend is likely ready.
start "" /min cmd /c "timeout /t 10 /nobreak >nul & start http://localhost:5173"

call npm run dev

echo.
echo Onboarding Automation System stopped.
pause
