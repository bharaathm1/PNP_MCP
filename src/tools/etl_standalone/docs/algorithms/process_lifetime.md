# Process Lifetime Module

## Overview
Tracks process creation, termination, and lifecycle events to understand process behavior and system resource allocation over time.

## Analysis Type
**Process Lifecycle and Resource Management Analysis**

## What It Extracts
- Process start and end times
- Process IDs and parent process relationships
- Process names and command lines
- Exit codes and termination reasons
- Process lifetime duration

## Data Source
**Method**: `trace.get_processes()` from SpeedLibs kernel

### ETW Events:
- Process/Start
- Process/Stop
- Process/DCStart (already running at trace start)
- Process/DCStop (still running at trace end)

## Output Format
```python
{
    'ProcessID': [1234, 5678, ...],
    'ProcessName': ['Teams.exe', 'chrome.exe', ...],
    'StartTime_ms': [0.0, 123.4, ...],
    'EndTime_ms': [5000.0, 6000.0, ...],
    'Duration_ms': [5000.0, 4876.6, ...],
    'ExitCode': [0, 0, 1, ...]
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `processlifetime()`
- **Lines**: Approximately 1120-1148

## Common Analyses

### 1. Short-Lived Processes
```python
# Find processes that started and stopped quickly
short_lived = process_df[process_df['Duration_ms'] < 1000]
```

### 2. Long-Running Processes
```python
# Identify persistent processes
long_running = process_df[process_df['Duration_ms'] > 10000]
```

### 3. Process Churn
```python
# Count process starts/stops
total_starts = len(process_df)
crashes = process_df[process_df['ExitCode'] != 0]
```

### 4. Parent-Child Relationships
```python
# Analyze process spawning patterns
# (if ParentPID available in data)
```

## Use Cases
- Identify frequently restarting services (potential issues)
- Track application startup/shutdown times
- Detect process crashes (non-zero exit codes)
- Analyze process churn during workload

## Integration
- Correlate with **Thread Statistics** for per-process thread behavior
- Use with **Process Statistics** for resource consumption
- Compare with **CPU Utilization** for process impact

## Related Analyses
- Process Statistics, Thread Statistics, CPU Utilization
