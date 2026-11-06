@echo off
REM Starts the Reader Service on port 8092 (syncs .venv with uv on each run).
REM LABEL: Reader Service
REM DESCRIPTION: Document OCR MCP tool server for Citadel and Ember (needs SGLangModel running).

cd /d "%~dp0"

uv sync
if errorlevel 1 (
    echo uv sync failed. Install uv: winget install astral-sh.uv
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

python -m src.run
pause
