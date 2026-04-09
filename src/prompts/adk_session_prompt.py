"""
ADK Session Manager Prompt - Guidance for managing PnP agent sessions with knowledge bases.

This prompt provides instructions for using ADK Session Manager tools along with
background knowledge about power rails and ETL dataframes for analysis.
"""

from app import mcp
from pathlib import Path
import json


@mcp.prompt(
    description=(
        "Comprehensive guide for ADK Session Manager tools with PnP agent analysis knowledge. "
        "Includes power rail debugging guidance and ETL dataframe usage patterns. "
        "**USE THIS AS SYSTEM PROMPT** to enable the LLM to answer domain questions without tool calls."
    ),
    tags={"adk", "session-manager", "pnp", "power-analysis", "etl", "system-prompt", "domain-knowledge"}
)
def adk_session_manager_prompt() -> str:
    """
    ADK Session Manager prompt with integrated knowledge bases.
    
    Returns a structured prompt with:
    1. Primary ADK session management instructions (highest priority)
    2. Power rail knowledge base (background reference)
    3. ETL dataframes knowledge base (background reference)
    """
    
    # Build the prompt with sections
    prompt_parts = []
    
    # Section 1: Primary Instructions (Highest Priority)
    primary_instructions = """
# ADK Session Manager - Primary Instructions

## ⚠️ CRITICAL: Answer Domain Knowledge Questions WITHOUT Tool Calls

**Before calling any tool, check if the question can be answered from the knowledge bases below.**

**Questions that should NOT trigger tool calls:**
- "What is WLC?" → Answer: WLC values (0=Idle, 1=Battery Life, 2=Sustained, 3=Bursty, 4=VC)
- "What power rails are available?" → Answer from Power Rail Knowledge Base
- "What dataframes can I query?" → Answer from ETL Dataframes Knowledge Base
- "What columns are in df_cpu_util?" → Answer from ETL knowledge
- "How do I calculate C0 residency?" → Answer from ETL knowledge

**Only call tools when:**
- User wants to analyze actual data (ETL files, power logs)
- User wants to load/process files
- User wants to compile reports
- Information is NOT in the knowledge bases

---

## CRITICAL: Agent Selection Rule

**If the user explicitly names an agent in their query, USE THAT AGENT EXACTLY.**

Examples:
- User says: "Select PowerSocwatchDataCompiler agent" → Use `agent_name="PowerSocwatchDataCompiler"`
- User says: "Use PnP to analyze" → Use `agent_name="PnP"`
- User says: "Switch to power_agent" → Use `agent_name="power_agent"`

**Do NOT override the user's explicit agent choice!**

---

## Quick Reference: Common Questions

### What is WLC?
**WLC (Workload Classification)** - System workload type classification

**WLC Values:**
- `0` = Idle
- `1` = Battery Life (light workload)
- `2` = Sustained (steady workload)
- `3` = Bursty (intermittent high activity)
- `4` = VC (Video Conference)

**DataFrame:** `df_wlc` (event-based, ~20-30 events per trace)
**Events:** `Microsoft-Windows-Kernel-Processor-Power/Diagnostic/WorkloadClassification`

To analyze WLC distribution, must resample to 1-second intervals with forward fill for accurate percentages.

### What ETL DataFrames are available?
- `df_cpu_util` - CPU utilization over time (~1000 rows)
- `df_thread_interval` - Thread execution intervals (1M+ rows, use filters!)
- `df_ppm_settings` - PPM configuration (~270 rows)
- `df_c0_intervals` - C-state intervals (700K+ rows, use time filters!)
- `df_wlc` - Workload classification (~20-30 events)
- `df_softparkselection` - Core parking decisions (~3500 rows)
- And 20+ more (see full list in ETL knowledge base below)

### What Power Rails are available?
**SOC Rails:** VCCCORE, VCCST, VCCGT, VCCSA, VCC_LP_ECORE, VDD2_CPU, etc.
**Platform Rails:** P_MEMORY, P_DISPLAY, P_BACKLIGHT, P_WLAN, P_SSD, P_VBATA

(Full details in Power Rail knowledge base below)

---

## Overview
The ADK Session Manager enables programmatic control of PnP (Power and Performance) agents 
with explicit state persistence. Use these tools for analyzing power, performance, and 
system behavior.

## Core Tool: adk_run_agent

Execute PnP agents with session persistence.

**Parameters:**
- agent_name: "PnP" (power/ETL orchestrator), "PowerSocwatchDataCompiler" (power+Socwatch compiler)
- query: Your analysis request (see workflows below)
- session_id: Unique identifier for saving/resuming sessions
- save_session: true (to persist state) or false (one-time query)

---

## Available Agents

### 1. PnP (Recommended for Most Tasks)
**Purpose:** Power and ETL analysis orchestrator

**Use Cases:**
- ETL trace analysis with DataFrame queries
- Power measurement analysis
- Multi-step analysis workflows
- General power/performance debugging

**Example:**
```json
{
  "agent_name": "PnP",
  "query": "Load and analyze E:\\trace.etl",
  "session_id": "etl_analysis_001"
}
```

### 2. PowerSocwatchDataCompiler
**Purpose:** Compile Power + Socwatch data into Excel summaries

**Use Cases:**
- Compiling measured power data from system under test
- Generating Socwatch data summaries
- Creating comprehensive Excel reports
- Combining power and Socwatch metrics

**Features:**
- Includes ETL_ANALYZER as sub-agent
- Windows-compatible
- Generates meaningful summary tables

**Example:**
```json
{
  "agent_name": "PowerSocwatchDataCompiler",
  "query": "Compile power and Socwatch data from D:\\measurements into summary Excel",
  "session_id": "power_compile_001"
}
```

---

## ETL Analysis Workflow (CRITICAL)

### Step 1: Initial ETL Load
**First query to load and process an ETL file:**

```python
result = adk_run_agent(
    agent_name="PnP",
    query="Load and analyze E:\\path\\to\\trace.etl",
    session_id="session_001",
    save_session=True
)
```

**Agent Response Contains:**
- ETL file path
- **Pickle file path** (IMPORTANT - save this!)
- Number of DataFrames available (e.g., 25)
- Processing time
- Debug log path

**Example Response:**
```
ETL: E:\\WCL\\HOPPER\\BusyIdle\\hopper_result_default.etl
Pickle file: C:\\Users\\...\\etl_analysis_hopper_result_default_1770863302.pkl
DataFrames available: 25
Processing time: 18.16 s
```

### Step 2: Follow-Up Queries (MUST Include Pickle File)

**CRITICAL:** All follow-up queries MUST reference the pickle file path to avoid re-processing the ETL.

**Correct Format:**
```python
result = adk_run_agent(
    agent_name="PnP",
    query="From df_thread_interval of <PICKLE_FILE_PATH>, list the unique processes (Process name and PID).",
    session_id="session_001",
    save_session=True
)
```

**Real Example:**
```python
result = adk_run_agent(
    agent_name="PnP",
    query="From df_thread_interval of C:\\Users\\bm1\\AppData\\Local\\Temp\\etl_analysis_hopper_result_default_1770863302.pkl, list the unique processes (Process name and PID).",
    session_id="session_001",
    save_session=True
)
```

**Query Pattern for DataFrame Analysis:**
```
From <DATAFRAME_NAME> of <PICKLE_FILE_PATH>, <your analysis request>
```

**Common Follow-Up Query Examples:**

1. **Get specific DataFrame data:**
   ```
   From df_cpu_util of <PICKLE_PATH>, calculate average CPU utilization for all cores
   ```

2. **Analyze time windows:**
   ```
   From df_thread_interval of <PICKLE_PATH>, show top 5 processes by CPU time between 10s and 20s
   ```

3. **Check specific metrics:**
   ```
   From df_ppm_settings of <PICKLE_PATH>, show all PerfIncreaseThreshold values for DC mode
   ```

4. **Compare states:**
   ```
   From df_softparkselection of <PICKLE_PATH>, calculate parking state distribution as percentage
   ```

5. **Get summary statistics:**
   ```
   From df_preprocessed of <PICKLE_PATH>, show statistics for CPU0 and CPU1
   ```

---

## Session Management

### Session Storage
- Sessions are stored in `PnP_agents/sessions/` directory
- State files: `{agent}_{session_id}.state.json` (contains pickle file path and dataframes)
- Session events: `{agent}_{session_id}.session.json`
- Resume sessions by using the same session_id

### State Persistence
The session state file preserves:
- Loaded pickle file paths
- DataFrame inventory (names, row counts, descriptions)
- Analysis context and conversation history
- Agent internal variables (DATAFRAMES_STORAGE, CONTEXT_INVENTORY)

---

## Best Practices

1. **Always save the pickle file path** returned from initial ETL load
2. **Include pickle file path** in all follow-up queries to avoid re-processing
3. **Use descriptive session_id** for complex multi-step analysis (e.g., "busyidle_feb13")
4. **Set save_session=True** to preserve context across multiple queries
5. **Reference dataframe names** from the etl_dataframes_knowledge_base (see below)
6. **Check available dataframes** after ETL load before querying specific ones

---

## Query Formatting Rules

✅ **Correct:**
- `From df_cpu_util of C:\\path\\to\\file.pkl, calculate average utilization`
- `From df_ppm_settings of <PICKLE_PATH>, show DC mode settings`

❌ **Incorrect (will cause re-processing):**
- `Analyze df_cpu_util` (missing pickle path)
- `Show CPU utilization in the trace` (ambiguous, no pickle reference)
- `From E:\\trace.etl, show processes` (referencing ETL instead of pickle)

---
"""
    prompt_parts.append(primary_instructions)
    
    # Section 2: Load Power Rail Knowledge Base
    try:
        # Load from local knowledge directory
        knowledge_dir = Path(__file__).parent / "knowledge"
        power_kb_file = knowledge_dir / "power_rail_knowledge_base.json"
        
        if power_kb_file.exists():
            with open(power_kb_file, 'r', encoding='utf-8') as f:
                power_rail_data = json.load(f)
            
            prompt_parts.append("\n# Background Knowledge: Power Rail Analysis\n\n")
            prompt_parts.append("*This knowledge helps answer questions about power rails without calling tools.*\n\n")
            
            # Simply dump the JSON content in a readable format
            prompt_parts.append(f"```json\n{json.dumps(power_rail_data, indent=2)}\n```\n")
                    
    except Exception as e:
        prompt_parts.append(f"\n# Power Rail Knowledge: (Unable to load: {str(e)})\n")
    
    # ========================================================================
    # DOMAIN KNOWLEDGE: Power Rails & ETL DataFrames
    # 
    # Purpose: Provide background knowledge to improve LLM responses
    # - Helps answer user questions without calling tools
    # - Improves query formulation when tools ARE needed
    # - NOT used for agent selection/delegation decisions
    # ========================================================================
    
    # Section 3: Load ETL Dataframes Knowledge Base
    try:
        # Load from local knowledge directory
        knowledge_dir = Path(__file__).parent / "knowledge"
        etl_kb_file = knowledge_dir / "etl_dataframes_knowledge_base.json"
        
        if etl_kb_file.exists():
            with open(etl_kb_file, 'r', encoding='utf-8') as f:
                etl_data = json.load(f)
            
            prompt_parts.append("\n---\n\n# Background Knowledge: ETL Dataframes\n\n")
            prompt_parts.append("*This knowledge helps answer questions about ETL analysis without calling tools.*\n\n")
            
            # Simply dump the JSON content in a readable format
            prompt_parts.append(f"```json\n{json.dumps(etl_data, indent=2)}\n```\n")
                    
    except Exception as e:
        prompt_parts.append(f"\n# ETL Dataframes Knowledge: (Unable to load: {str(e)})\n")
    
    # Footer
    prompt_parts.append("\n---\n\n")
    prompt_parts.append("## How to Use This Prompt\n\n")
    prompt_parts.append("**Priority Order:** Primary Instructions > Power Rail Knowledge > ETL Dataframes Knowledge\n\n")
    prompt_parts.append("**Purpose of Knowledge Bases:**\n")
    prompt_parts.append("- Answer user questions directly (e.g., 'what is WLC?' → answer without tool call)\n")
    prompt_parts.append("- Improve queries when tools ARE needed (e.g., know which dataframe to query)\n")
    prompt_parts.append("- Provide context for interpreting agent responses\n")
    prompt_parts.append("- **NOT for agent selection/delegation decisions** (use explicit agent_name parameter)\n\n")
    
    return "".join(prompt_parts)
