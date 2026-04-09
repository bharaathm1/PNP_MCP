@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   MCP Servers Bundle Setup
echo ============================================================
echo.

:: ── Check Python ──────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Found %PYVER%

:: ── Create venv ───────────────────────────────────────────────
if exist venv\ (
    echo [OK] venv already exists — skipping creation
) else (
    echo [..] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Ensure python -m venv is available.
        pause
        exit /b 1
    )
    echo [OK] Created venv\
)

:: ── Install packages ──────────────────────────────────────────
echo [..] Installing dependencies from requirements.txt...
call venv\Scripts\pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check requirements.txt and your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed
:: ── Seed power rail knowledge base ──────────────────────────────
echo [..] Seeding power rail knowledge base (one-time)...
call venv\Scripts\python.exe seed_knowledge.py
if errorlevel 1 (
    echo [WARN] Power rail seed step failed - will use JSON fallback at runtime.
) else (
    echo [OK] Power rail knowledge base ready
)
:: ── Create .env if missing ────────────────────────────────────
if not exist .env (
    echo [..] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [OK] Created .env — edit it to set SERVER_NAME, ENVIRONMENT, etc.
) else (
    echo [OK] .env already exists
)

:: ── Create .vscode/mcp.json if missing ───────────────────────
if not exist .vscode\mcp.json (
    echo [..] Creating .vscode\mcp.json from template...
    copy .vscode\mcp-config-template.json .vscode\mcp.json >nul
    echo [OK] Created .vscode\mcp.json — uses $"{workspaceFolder}" so it works anywhere
) else (
    echo [OK] .vscode\mcp.json already exists
)

:: ── Done ──────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Setup complete!
echo.
echo   Next steps:
echo     1. Open THIS folder in VS Code:
echo           code .
echo     2. When prompted, allow the MCP servers to start.
echo     3. In Copilot Chat, click the tools icon to see
echo        "etl-analysis" and "power-socwatch" tools.
echo ============================================================
echo.
pause
