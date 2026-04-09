# MCP Servers Bundle

Local MCP servers for **ETL trace analysis** and **Power + SocWatch** telemetry,
designed to run in VS Code via stdio transport (no manual server start required).

VS Code spawns these processes automatically — no ports, no URLs, no auth tokens.
**Self-contained:** everything needed is inside this single folder. Just copy it anywhere and run `setup.bat`.

---

## Prerequisites

- VS Code 1.99+ with GitHub Copilot extension
- Python 3.11+ on PATH
- **No MongoDB required** — the knowledge base uses a pure-Python local store (`mongita`), installed automatically by `setup.bat`

---

## Setup (one-time, per machine)

### 1. Run setup.bat

Double-click `setup.bat` in this folder, or run it from a terminal:

```cmd
setup.bat
```

This will:
- Create a `venv\` inside this folder
- Install all Python dependencies into it (including `mongita` for the knowledge base)
- Seed the Power Rail Knowledge Base into a local file store (`data/mongita/`)
- Create a `.env` file from `.env.example`

> **Re-seed after updating the knowledge JSON:**
> ```cmd
> venv\Scripts\python.exe seed_knowledge.py --force
> ```

### 2. Open this folder in VS Code

```cmd
code .
```

Make sure you open **this exact folder** as the workspace root — `mcp.json` uses
`${workspaceFolder}` to find the venv.

### 3. Reload VS Code window

`Ctrl+Shift+P` → **Developer: Reload Window**

VS Code reads `.vscode/mcp.json`, spawns the Python processes, and makes the tools
available in Copilot Chat automatically.

---

## Verify

In Copilot Chat, click the **Tools (🔧)** icon. You should see:

| Server | Example tools |
|---|---|
| `etl-analysis` | `discover_etl_files`, `run_standalone_script`, `load_dataframes_from_pickle` |
| `power-socwatch` | `find_power_summary_files`, `find_socwatch_files`, `parse_socwatch_data` |

Quick sanity prompt:

```
What ETL and power analysis tools are available?
```

---

## Folder Structure

```
fastmcp-stdio-servers/          ← this bundle (open as VS Code workspace root)
  etl_stdio.py                  ← ETL server entry point (stdio)
  power_socwatch_stdio.py       ← Power+SocWatch server entry point (stdio)
  setup.bat                     ← one-time setup: creates venv + installs deps + seeds KB
  seed_knowledge.py             ← standalone KB re-seed script (run with --force to refresh)
  requirements.txt              ← pinned dependencies
  .env.example                  ← copy to .env and customise
  .env                          ← your local config (created by setup.bat)
  src/                          ← tool implementations (app, tools, prompts, utils)
  config/                       ← settings module
  data/mongita/                 ← local knowledge base store (created by setup.bat)
  venv/                         ← Python virtual environment (created by setup.bat)
  .vscode/
    mcp.json                    ← active MCP config (uses ${workspaceFolder}\venv)
    mcp-config-template.json    ← reference copy
    settings.json               ← enables chat.mcp.enabled
```

---

## Sharing with the Team

Just zip the folder **without** `venv\`:

```powershell
# From the parent folder
Compress-Archive -Path fastmcp-stdio-servers -DestinationPath mcp-servers.zip `
  -CompressionLevel Optimal
```

> `venv\` is large and machine-specific — teammates regenerate it with `setup.bat`.

Recipient steps:
1. Unzip to any folder
2. Run `setup.bat`
3. `code .` to open in VS Code
4. Reload window

---

## How It Works

Unlike HTTP servers (which you start manually and connect to via URL), stdio servers
are process-per-user: VS Code starts a fresh Python process for each user, communicates
over stdin/stdout, and stops it when the session ends. No shared state, no port conflicts.

```
VS Code Copilot Chat
      ↓  (reads .vscode/mcp.json)
      ↓  spawns: venv\Scripts\python.exe etl_stdio.py
      ↓  ←—stdin/stdout—→  FastMCP (stdio mode)
      ↓  tools: discover_etl_files, run_standalone_script, ...
```
