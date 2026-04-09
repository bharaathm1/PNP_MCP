# Thread Statistics Module

## Overview
Comprehensive thread-level execution metrics including execution time, context switches, wait times, and thread state transitions.

## Analysis Type
**Thread Performance and Scheduling Analysis**

## What It Extracts
- Thread execution times and intervals
- Context switch counts per thread
- Thread state transitions (running, waiting, ready)
- Per-thread CPU time and cycles
- Thread priority and affinity

## Data Source
**Method**: `trace.get_thread_intervals()` from SpeedLibs kernel

### Typical Columns:
- ThreadID, ProcessID, ProcessName
- Start time, End time, Duration
- State (Running, Waiting, Ready)
- CPU number, Priority
- Context switch count

## Output Format
```python
{
    'ThreadID': [1234, 5678, ...],
    'ProcessName': ['Teams.exe', 'chrome.exe', ...],
    'ExecutionTime_ms': [123.4, 456.7, ...],
    'ContextSwitches': [45, 123, ...],
    'State': ['Running', 'Waiting', ...]
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `threadstat()`
- **Lines**: Approximately 1095-1120

## Common Analyses

### 1. Top Threads by CPU Time
```python
top_threads = thread_df.nlargest(10, 'ExecutionTime_ms')
```

### 2. Context Switch Analysis
```python
high_switches = thread_df[thread_df['ContextSwitches'] > 1000]
# High context switches may indicate scheduling issues
```

### 3. Thread State Distribution
```python
state_counts = thread_df['State'].value_counts()
```

## Integration
- Use with **Process Statistics** for per-process thread analysis
- Correlate with **CPU Utilization** for core usage patterns
- Compare with **QoS** data for priority compliance

## Related Analyses
- Process Statistics, CPU Utilization, QoS, Hetero Response
