# CPU Utilization Module

## Overview
Calculates per-core CPU utilization percentages over time, showing how busy each processor core is during the trace.

## Analysis Type
**Core-Level CPU Usage Analysis**

## What It Extracts
- Utilization percentage per CPU core
- Idle vs active time breakdown
- Time series of utilization values
- Per-core load distribution

## Data Source

### Method:
`trace.get_cpu_utilization()` from SpeedLibs kernel

### Calculation:
```
Utilization% = (Active_Time / Total_Time) * 100
```

Where:
- Active_Time = Time core spent executing threads
- Total_Time = Trace duration
- Idle_Time = Total_Time - Active_Time

## Output Format
```python
{
    'CPU': [0, 1, 2, 3, ...],
    'Utilization_%': [45.2, 67.8, 23.1, 89.3, ...],
    'ActiveTime_ms': [4520, 6780, 2310, 8930, ...],
    'IdleTime_ms': [5480, 3220, 7690, 1070, ...]
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `get_cpu_utilization()`
- **Lines**: Approximately 1050-1080

## Common Analyses

### 1. Overall System Load
```python
avg_util = cpu_util_df['Utilization_%'].mean()
print(f"Average CPU utilization: {avg_util:.1f}%")
```

### 2. Core Balance
```python
std_dev = cpu_util_df['Utilization_%'].std()
# High std_dev indicates unbalanced load
if std_dev > 20:
    print("WARNING: Unbalanced core usage")
```

### 3. Identify Hotspot Cores
```python
hotspots = cpu_util_df[cpu_util_df['Utilization_%'] > 80]
print(f"Cores running hot: {hotspots['CPU'].tolist()}")
```

### 4. P-core vs E-core Comparison
```python
# Assuming cores 0-7 are P-cores, 8-15 are E-cores
p_cores = cpu_util_df[cpu_util_df['CPU'] < 8]['Utilization_%'].mean()
e_cores = cpu_util_df[cpu_util_df['CPU'] >= 8]['Utilization_%'].mean()
print(f"P-core avg: {p_cores:.1f}%, E-core avg: {e_cores:.1f}%")
```

## Utilization Categories

| Range | Classification | Interpretation |
|-------|----------------|----------------|
| 0-10% | Idle | Core mostly unused |
| 10-30% | Light | Occasional activity |
| 30-60% | Moderate | Balanced usage |
| 60-80% | Heavy | Frequent activity |
| 80-100% | Saturated | Core fully loaded |

## Use Cases
- Identify performance bottlenecks (saturated cores)
- Assess workload parallelism
- Validate scheduler efficiency
- Detect core parking effectiveness
- Compare P-core vs E-core usage

## Integration
- Compare with **Hetero Response** for core type efficiency
- Correlate with **WLC** for workload impact
- Check against **Containment** for parking policy effectiveness
- Review with **Thread Statistics** for thread distribution

## Performance Indicators

### Good Signs:
- ✅ Balanced utilization across cores
- ✅ Low variance (similar util across cores)
- ✅ No cores consistently at 100%
- ✅ Idle cores during light workload

### Warning Signs:
- ⚠️ One core at 100%, others idle (poor parallelism)
- ⚠️ All cores at 100% (system overloaded)
- ⚠️ High utilization on E-cores only (P-cores not being used)
- ⚠️ Zero idle time (no headroom for bursts)

## Related Analyses
- CPU Frequency, Hetero Response, WLC, Thread Statistics, Containment Policy
