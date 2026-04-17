# SPEED API Reference for Standalone Script Generation

## Coding Instructions

1. **Read these docs** to understand the available Python APIs before writing analysis code.
2. **Do NOT use Jupyter notebooks.** Write a standalone `.py` file that runs via `speed.exe run <script>.py --etl_file <path>`.
3. **Be concise** — convert the user requirement to accurate analysis code without boilerplate bloat.
4. **Use high-level API when possible** (`get_c0_intervals`, `get_cpu_frequencies`, etc.) before falling back to `get_events`.
5. **If the requirement is ambiguous**, ask for clarification before generating code.
6. **PKL output standard:** save results as a `dict` with named `pd.DataFrame` values using `pickle.dump(data, f)`. Key name must match `output_key`.

---

## Trace Loading

```python
import tracedm

trace = tracedm.load_trace(etl_file="path/to/file.etl")
# optional with EMON:
trace = tracedm.load_trace(etl_file="file.etl", emon_file="emon.csv")
```

The returned `trace` object exposes:
- `trace.os_trace` — the `IEventTrace` interface (all methods below)
- `trace.get_events(...)` — shortcut equivalent to `trace.os_trace.get_events(...)`
- `trace.os_trace.duration` — total trace duration in seconds
- `trace.os_trace.base_timestamp` — trace base timestamp

---

## High-Level IEventTrace APIs (prefer these)

### C0 Intervals (active/non-idle CPU state)
```python
df = trace.os_trace.get_c0_intervals(
    time_range=(start_s, end_s),  # optional
    physical=False,               # True = physical cores, False = logical
    summary=False,                # True = total duration per core
    package=False,                # True = package-level C0
    cpus=None,                    # list of cpu ids to include
)
# Returns: DataFrame with Start(s), End(s), CPU, Duration(s), State columns
```

### CPU Concurrency
```python
df = trace.os_trace.get_cpu_concurrency(
    time_range=(start_s, end_s),  # optional
    summary=False,                # True = Count + Duration
    physical=False,
    sample_period=None,           # float seconds, if specified resamples data
    cpus=None,
)
# Returns: DataFrame with Count, Start(s), End(s), Duration(s)
```

### CPU Frequencies
```python
df = trace.os_trace.get_cpu_frequencies(
    time_range=(start_s, end_s),  # optional
    physical=False,
    sample_period=None,           # float seconds, if specified samples data
    summary=False,                # True = per-core weighted mean frequency
)
# Returns: DataFrame with Start(s), End(s), CPU, Frequency(Hz), Duration(s)
```

### CPU Utilization
```python
df = trace.os_trace.get_cpu_utilization(
    time_range=(start_s, end_s),  # optional
    sample_period=0.1,            # sampling period in seconds (default: 0.1)
    physical=False,
    summary=False,                # True = average per-core utilization Series
)
# Returns: DataFrame with time index (seconds) and per-cpu C0 % columns
```

### Processes
```python
df = trace.os_trace.get_processes(time_range=(start_s, end_s))
# Returns: DataFrame with Process, PID, Start(s), End(s), Duration columns
```

### Context Switches
```python
df = trace.os_trace.get_context_switches(time_range=(start_s, end_s))
# Returns: DataFrame with old/new thread, CPU, wait reason
```

### Disk Intervals
```python
df = trace.os_trace.get_disk_intervals(time_range=(start_s, end_s))
# Returns: DataFrame with Queue(s), Start(s), End(s), Duration(s), CPU,
#          Process, PID, TID, DiskNum, Type, #Bytes, File
```

### GPU Frames
```python
df = trace.os_trace.get_gpu_frames(time_range=(start_s, end_s), process="myapp.exe")
# Returns: DataFrame with Start(s), End(s), Duration(s), Process, PID, TID
```

### GPU Intervals
```python
df = trace.os_trace.get_gpu_intervals(time_range=(start_s, end_s))
# Returns: DataFrame with Start(s), End(s), Process, PID, TID, Engine, Duration(s)
```

### Power Profile Intervals
```python
df = trace.os_trace.get_power_profile_intervals(time_range=(start_s, end_s), summary=False)
# Returns: DataFrame with Start(s), End(s), CPU, Name, Duration(s)
```

### Parked Core Intervals
```python
df = trace.os_trace.get_parked_core_intervals(time_range=(start_s, end_s))
# Returns: DataFrame with parked core state per CPU
```

### Event Intervals (start/stop pairs)
```python
df = trace.os_trace.get_event_intervals(
    event='Microsoft-Windows-MSMPEG2VDEC/DXVA_BeginFrame',
    # OR: start='...win:Start', end='...win:Stop'
    time_range=(start_s, end_s),
)
# Returns: DataFrame with Time(s), CPU, Process, PID, TID, Name
```

---

## Low-Level Event Iteration (fallback when no high-level API exists)

```python
# Iterate all events:
for ev in trace.get_events():
    ts  = ev["TimeStamp"]       # float, seconds from trace start
    name = ev["EventName"]      # e.g. "Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info"
    pid  = ev["ProcessId"]
    cpu  = ev["CPU"]

# Filter by event type (full event name including opcode):
evts = trace.get_events(
    event_types=["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info"]
)

# Filter by provider name only (matches all events from that provider):
evts = trace.get_events(
    event_types=["Microsoft-Windows-Kernel-Processor-Power"]
)

# Combined filter + time range:
evts = trace.get_events(
    event_types=["Provider/EventName/win:Info"],
    time_range=(5.0, 65.0),
)

# Access event-specific fields (varies per event):
for ev in evts:
    value = ev["FieldName"]   # raises KeyError if field not present — use ev.get("FieldName")
```

**DO NOT import or use:** `speed.explorer`, `ev.filter_provider`, `tracedm.events`, or any other invented module path.

---

## Standard ETW Event Name Format

```
<Provider>/<EventName>/<Opcode>
```
Examples:
- `Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info`
- `Microsoft-Windows-Kernel-Processor-Power/WpsContainmentUnparkCount/win:Info`
- `Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info`
- `Microsoft-Windows-Kernel-Processor-Power/ProfileSettingChange/win:Info`
- `DptfCpuEtwProvider/WLC_SOCWC_Classification/win:Info`

Use `standalone_extract_unique_events.py` (PKL key: `unique_events`) to discover available event names in an ETL file.

---

## PKL Output Convention

```python
import pickle, os
from datetime import datetime

PKL_SUFFIX = "my_metric"   # determines output filename

def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

# Save:
data = {
    "df_my_metric": df,          # primary DataFrame
    "meta": {                    # always include meta
        "analysis": PKL_SUFFIX,
        "etl_file": etl_file_path,
        "timestamp": datetime.now().isoformat(),
    }
}
with open(pkl_path, "wb") as f:
    pickle.dump(data, f)
```

---

## numpy Compatibility Patch (required for older traces)

```python
import numpy as np
if not hasattr(np, "int"):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool
```

---

## Typical Script Structure

```python
"""
Standalone: my_metric
=======================
Description of what this script does.

PKL: <etl_basename>_my_metric.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_my_metric.py --etl_file <path>

PKL keys:
    df_my_metric — description of columns
"""
import sys, os, argparse, pickle
from datetime import datetime
import pandas as pd
import numpy as np
if not hasattr(np, "int"):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
except ImportError as e:
    print(f"[ERROR] {e}"); sys.exit(1)

PKL_SUFFIX = "my_metric"

def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def run_analysis(trace, etl_file_path: str) -> dict:
    # --- YOUR ANALYSIS CODE HERE ---
    # Use high-level APIs first, fall back to get_events() for custom ETW events
    rows = []
    for ev in trace.get_events(event_types=["Provider/EventName/win:Info"]):
        rows.append({"timestamp": ev["TimeStamp"], "value": ev["FieldName"]})
    df_my_metric = pd.DataFrame(rows)
    return {"df_my_metric": df_my_metric}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
    trace = tracedm.load_trace(etl_file=args.etl_file)
    data = run_analysis(trace, args.etl_file)
    data["meta"] = {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                    "timestamp": datetime.now().isoformat()}
    with open(pkl, "wb") as f:
        pickle.dump(data, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
```
