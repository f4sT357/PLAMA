@echo off
:: PLAMA v1.4 Startup Script
:: Prerequisites: Python 3.11+, LM Studio running on localhost:1234

setlocal

set PLAMA_ROOT=%~dp0
set BACKEND=%PLAMA_ROOT%backend
set MEMORY_DIR=%PLAMA_ROOT%memory_data
set FRONTEND=%PLAMA_ROOT%frontend

:: Create memory_data dirs if missing
if not exist "%MEMORY_DIR%" mkdir "%MEMORY_DIR%"
if not exist "%MEMORY_DIR%\chroma_store" mkdir "%MEMORY_DIR%\chroma_store"
if not exist "%MEMORY_DIR%\corpus_store" mkdir "%MEMORY_DIR%\corpus_store"

:: Set env vars
set PLAMA_MEMORY_DIR=%MEMORY_DIR%
set PLAMA_DEDUP_THRESHOLD=0.12
set PLAMA_MID_SESSION_THRESHOLD=20

echo.
echo ╔══════════════════════════════════════╗
echo ║   PLAMA v1.4 - Starting...          ║
echo ╚══════════════════════════════════════╝
echo.
echo [1/3] Checking LM Studio connection...
curl -s http://localhost:1234/v1/models >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] LM Studio not detected at localhost:1234
    echo        Please start LM Studio before chatting.
) else (
    echo [OK]  LM Studio connected.
)

echo.
echo [2/3] Starting PLAMA backend (FastAPI)...
start "PLAMA Backend" cmd /k "cd /d %BACKEND% && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo.
echo [3/3] Starting PLAMA frontend (Next.js)...
if exist "%FRONTEND%\package.json" (
    start "PLAMA Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"
) else (
    echo [SKIP] Frontend not found at %FRONTEND%
    echo        Run: npx create-next-app@latest frontend
)

echo.
echo ══════════════════════════════════════════
echo  PLAMA v1.4 started.
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:3000
echo  API docs: http://localhost:8000/docs
echo ══════════════════════════════════════════
echo.
pause
