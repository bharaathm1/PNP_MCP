# WLC (Workload Classification) Module

## Overview
Extracts and analyzes workload classification data from DPTF (Dynamic Platform and Thermal Framework) CPU ETW Provider events to understand system workload patterns.

## Analysis Type
**Workload Classification and Pattern Detection**

## What It Extracts
- SOCWC (System-on-Chip Workload Classification) status over time
- Workload state transitions
- Classification patterns during trace

## Data Source

### ETW Provider:
- **Provider**: `DptfCpuEtwProvider`
- **Event Level**: `win:Info`
- **Target String**: `"SOCWC classification = "`

### Event Fields:
```python
event["String"] == "SOCWC classification = "
event["Status"]      # WLC classification state
event["TimeStamp"]   # Event timestamp (microseconds)
```

## Extraction Process

### Step 1: Get DPTF Events
```python
event_type_list = ["DptfCpuEtwProvider//win:Info"]
events = trace.get_events(
    event_types=event_type_list,
    time_range=trace.time_range
)
```

### Step 2: Filter for WLC Events
```python
for event in events:
    if event["String"] == "SOCWC classification = ":
        timestamp.append(event["TimeStamp"] / 1000000)  # Convert to ms
        wlc_status.append(event["Status"])
```

### Step 3: Create DataFrame
```python
df = pd.DataFrame({
    "timestamp": timestamp,  # Time in milliseconds
    "wlc": wlc_status        # Classification state
})
```

## Output Format

### DataFrame Structure:
```python
{
    'timestamp': [0.123, 0.456, 0.789, ...],  # Milliseconds
    'wlc': [0, 1, 2, 1, 0, ...]               # Classification states
}
```

### Typical Column Values:
| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| `timestamp` | float | Time in milliseconds | 0.123, 1.456, 2.789 |
| `wlc` | int | Workload classification state | 0, 1, 2, 3 |

## WLC States

### Common Classifications:
| State | Meaning | Typical Scenario |
|-------|---------|------------------|
| **0** | Idle/Low activity | System idle, background tasks |
| **1** | Light workload | Web browsing, document editing |
| **2** | Medium workload | Video playback, light compilation |
| **3** | Heavy workload | Gaming, video encoding, stress test |

*Note: Exact state meanings may vary by platform implementation*

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `wlc()`
- **Lines**: Approximately 666-721

## Usage Patterns

### Standalone Usage:
```python
from speedlibs_clean import EtlTrace

# Create trace object
etl_trace = EtlTrace(trace_obj)

# Extract WLC data
wlc_df = etl_trace.wlc()

# Analyze workload patterns
print(f"Unique WLC states: {wlc_df['wlc'].unique()}")
print(f"Time range: {wlc_df['timestamp'].min():.2f} - {wlc_df['timestamp'].max():.2f} ms")
print(f"Total WLC events: {len(wlc_df)}")
```

### Via Trace Summary:
```python
result = get_trace_summary(etl_path="path/to/trace.etl")

# WLC data may be included in summary
# Access via result dictionary or pickle file
```

## Analysis Insights

### 1. Workload Pattern Detection
```python
# Find predominant workload state
most_common_state = wlc_df['wlc'].mode()[0]
state_duration = wlc_df.groupby('wlc')['timestamp'].count()
print(f"Most common state: {most_common_state}")
print(f"State distribution:\n{state_duration}")
```

### 2. State Transition Analysis
```python
# Count state changes
state_changes = (wlc_df['wlc'] != wlc_df['wlc'].shift()).sum()
print(f"Total state transitions: {state_changes}")

# Find rapid transitions (unstable workload)
time_diffs = wlc_df['timestamp'].diff()
rapid_transitions = time_diffs[time_diffs < 10]  # <10ms transitions
print(f"Rapid transitions: {len(rapid_transitions)}")
```

### 3. Time-in-State Calculation
```python
# Calculate time spent in each state
wlc_df['duration'] = wlc_df['timestamp'].diff().shift(-1)
time_per_state = wlc_df.groupby('wlc')['duration'].sum()
print(f"Time per state (ms):\n{time_per_state}")
```

## Typical Output

### Sample Console Output:
```
[WLC] Processed 15234 events, found 892 WLC classification events
[WLC] Extracted 892 entries
[WLC] Time range: 0.12 - 59832.45 ms
[WLC] Unique WLC states: [0 1 2]
```

### Sample DataFrame:
```
     timestamp  wlc
0        0.123    0
1       12.456    1
2       24.789    1
3       36.123    2
4       48.456    1
5       60.789    0
```

## Interpretation Guide

### Healthy Pattern:
```
Stable states: Long durations in appropriate states
Smooth transitions: State changes follow workload changes
Expected range: States match actual system activity
```

### Problematic Patterns:
```
Rapid oscillation: Many transitions <10ms (unstable classification)
Stuck state: No transitions despite workload changes
Unexpected state: Heavy workload classified as idle
```

## Integration with Other Analyses

### Correlate with CPU Utilization:
```python
# Compare WLC state with actual CPU usage
cpu_util_df = etl_trace.get_cpu_utilization()
merged = pd.merge_asof(
    wlc_df.sort_values('timestamp'),
    cpu_util_df.sort_values('timestamp'),
    on='timestamp'
)

# Check if WLC matches utilization
print(merged[['wlc', 'utilization']].corr())
```

### Correlate with Frequency:
```python
# Compare WLC with CPU frequency
freq_df = etl_trace.get_cpu_freq()
merged = pd.merge_asof(wlc_df, freq_df, on='timestamp')

# Verify frequency scaling matches workload classification
```

## Performance Considerations

### Event Density:
- Typical: 10-50 WLC events per second
- High activity: 50-200 events per second
- Low activity: <10 events per second

### Processing Time:
- Small trace (1 min): <1 second
- Medium trace (10 min): 2-5 seconds
- Large trace (60 min): 10-20 seconds

## Troubleshooting

### No WLC Data:
```python
if wlc_df.empty:
    print("[WARNING] No WLC data found")
    # Possible causes:
    # 1. DPTF not enabled on platform
    # 2. ETW provider not running
    # 3. Insufficient trace duration
    # 4. Trace collection without DPTF events
```

### Sparse Data:
```python
if len(wlc_df) < 10:
    print("[WARNING] Very few WLC events")
    # May indicate:
    # - Very short trace duration
    # - System mostly idle
    # - Incomplete trace collection
```

## Related Analyses
- **CPU Frequency**: WLC should correlate with frequency changes
- **CPU Utilization**: WLC state should match utilization levels
- **Power States**: WLC affects power management decisions
- **Hetero Response**: WLC influences P-core vs E-core selection

## Platform Dependencies

### Requirements:
- DPTF (Dynamic Platform and Thermal Framework) enabled
- DptfCpuEtwProvider active during trace collection
- Windows ETW infrastructure

### Platform-Specific:
- Different platforms may use different WLC state values
- Classification thresholds vary by platform
- Some older platforms may not support SOCWC
