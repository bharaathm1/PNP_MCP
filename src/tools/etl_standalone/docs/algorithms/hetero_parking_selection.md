# Hetero Parking Selection Module

## Overview
Tracks the Windows scheduler's decision-making process for selecting which specific cores (Performance or Efficiency) to unpark when more processing power is needed on hybrid CPU architectures.

## Analysis Type
**Core Selection and Parking Policy Analysis**

## What It Tracks
- Which core type is selected for unparking (P-cores vs E-cores)
- Total cores unparked at each decision point
- Distribution between Performance and Efficiency cores
- Containment policy influence on selection
- Core activation patterns over time

## Data Source

### ETW Provider:
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Event**: `HeteroParkingSelection`
- **Event Level**: `win:Info`

### Event Fields:
```python
event["TimeStamp"]                        # Event time (microseconds)
event["ContainmentEnabled"]               # Containment policy active (0/1)
event["TotalCoresUnparkedCount"]          # Total cores currently unparked
event["PerformanceCoresUnparkedCount"]    # P-cores currently unparked
event["EfficiencyCoresUnparkedCount"]     # E-cores currently unparked
```

## Output Format

### DataFrame Structure:
```python
{
    'timestamp': [0.123, 0.456, ...],
    'ContainmentEnabled': [1, 1, 0, ...],
    'TotalCoresUnparkedCount': [4, 8, 12, ...],
    'PerformanceCoresUnparkedCount': [0, 0, 4, ...],
    'EfficiencyCoresUnparkedCount': [4, 8, 8, ...]
}
```

## Key Concepts

### Parking Policy:
When system needs more cores, scheduler decides:
1. **With Containment**: Prefer E-cores first, P-cores only when needed
2. **Without Containment**: Use any available cores for best performance

### Selection Strategy:
```
Light load → Unpark E-cores only
Medium load → Unpark all E-cores, then add P-cores
Heavy load → Unpark all E-cores + all P-cores
```

## Analysis Patterns

### 1. Core Type Preference
```python
# Calculate E-core vs P-core usage ratio
total_ecore_time = df['EfficiencyCoresUnparkedCount'].sum()
total_pcore_time = df['PerformanceCoresUnparkedCount'].sum()
ratio = total_ecore_time / (total_pcore_time + 1)  # Avoid division by zero

if ratio > 2.0:
    print("E-core preferred (power efficient)")
elif ratio > 1.0:
    print("Balanced E-core and P-core usage")
else:
    print("P-core preferred (performance mode)")
```

### 2. Parking Ramp-Up Pattern
```python
# Analyze how cores are activated
df['pcore_added'] = df['PerformanceCoresUnparkedCount'].diff()
df['ecore_added'] = df['EfficiencyCoresUnparkedCount'].diff()

# Check if E-cores are maxed before P-cores activate
ecore_max = df['EfficiencyCoresUnparkedCount'].max()
first_pcore = df[df['PerformanceCoresUnparkedCount'] > 0].iloc[0]
ecore_at_first_pcore = first_pcore['EfficiencyCoresUnparkedCount']

if ecore_at_first_pcore >= ecore_max * 0.8:
    print("✓ Good: E-cores near max before P-cores activate")
else:
    print("⚠ Warning: P-cores activated with E-cores underutilized")
```

### 3. Containment Impact
```python
# Compare behavior with/without containment
with_containment = df[df['ContainmentEnabled'] == 1]
without_containment = df[df['ContainmentEnabled'] == 0]

print(f"With containment:")
print(f"  Avg E-cores: {with_containment['EfficiencyCoresUnparkedCount'].mean():.1f}")
print(f"  Avg P-cores: {with_containment['PerformanceCoresUnparkedCount'].mean():.1f}")

print(f"Without containment:")
print(f"  Avg E-cores: {without_containment['EfficiencyCoresUnparkedCount'].mean():.1f}")
print(f"  Avg P-cores: {without_containment['PerformanceCoresUnparkedCount'].mean():.1f}")
```

### 4. Core Activation Timeline
```python
# Identify significant parking changes
df['total_change'] = df['TotalCoresUnparkedCount'].diff()
significant_changes = df[abs(df['total_change']) >= 2]  # 2+ cores changed
print(f"Significant parking events: {len(significant_changes)}")
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `heteroparkingselection()`
- **Lines**: Approximately 806-843

## Usage Patterns

### Standalone Usage:
```python
from speedlibs_clean import EtlTrace

etl_trace = EtlTrace(trace_obj)
parking_df = etl_trace.heteroparkingselection()

# Analyze core distribution
print(f"Max E-cores used: {parking_df['EfficiencyCoresUnparkedCount'].max()}")
print(f"Max P-cores used: {parking_df['PerformanceCoresUnparkedCount'].max()}")
print(f"Max total cores: {parking_df['TotalCoresUnparkedCount'].max()}")
```

## Interpretation Guide

### Optimal Parking Selection:
```
✓ E-cores unparked first for light workloads
✓ E-cores maxed out before P-cores activate
✓ Smooth ramp-up (gradual core activation)
✓ P-cores park quickly when workload decreases
```

### Suboptimal Patterns:
```
✗ P-cores activate while E-cores idle
✗ Aggressive P-core activation for light loads
✗ Slow P-core parking (wastes power)
✗ Oscillation (rapid park/unpark cycles)
```

## Common Scenarios

### Scenario 1: Light Web Browsing
```
ContainmentEnabled: 1
TotalCoresUnparkedCount: 2-4
PerformanceCoresUnparkedCount: 0
EfficiencyCoresUnparkedCount: 2-4
→ Only E-cores needed, power efficient
```

### Scenario 2: Video Encoding
```
ContainmentEnabled: 1
TotalCoresUnparkedCount: 12-16
PerformanceCoresUnparkedCount: 4-6
EfficiencyCoresUnparkedCount: 8 (all)
→ All E-cores + some P-cores for heavy work
```

### Scenario 3: Performance Mode (Gaming)
```
ContainmentEnabled: 0
TotalCoresUnparkedCount: 16+ (all cores)
PerformanceCoresUnparkedCount: 8 (all)
EfficiencyCoresUnparkedCount: 8 (all)
→ All cores available, maximum performance
```

## Performance Implications

### Power Efficiency:
- More E-core usage = 2-3x better power efficiency
- Delayed P-core activation saves battery
- Quick P-core parking reduces idle power

### Responsiveness:
- Slow P-core activation = laggy interactive apps
- Premature P-core activation = wasted power
- Oscillation = inconsistent performance

### Thermal Management:
- P-cores generate more heat
- E-cores allow better thermal headroom
- Balanced usage prevents throttling

## Integration with Other Analyses

### With WPS Containment Unpark:
- WPS decides HOW MANY cores to unpark
- Hetero Parking Selection decides WHICH cores

### With Hetero Response:
- Thread promotions should trigger P-core unparking
- Thread demotions allow P-core parking

### With CPU Utilization:
- Unparked cores should show actual utilization
- Parked cores should be idle

### With Power States:
- Parked cores can enter deep C-states
- Unparked cores limited to shallow C-states

## Visualization Recommendations

### Stacked Area Chart:
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 6))

# Stacked area showing core types
ax.fill_between(parking_df['timestamp'], 
                0, 
                parking_df['EfficiencyCoresUnparkedCount'],
                label='E-cores', color='blue', alpha=0.6)
ax.fill_between(parking_df['timestamp'],
                parking_df['EfficiencyCoresUnparkedCount'],
                parking_df['TotalCoresUnparkedCount'],
                label='P-cores', color='red', alpha=0.6)

ax.set_xlabel('Time (ms)')
ax.set_ylabel('Unparked Cores')
ax.set_title('Core Parking Selection Over Time')
ax.legend()
ax.grid(True, alpha=0.3)
```

### Core Type Ratio:
```python
# Pie chart of core usage
ecore_total = parking_df['EfficiencyCoresUnparkedCount'].sum()
pcore_total = parking_df['PerformanceCoresUnparkedCount'].sum()

plt.figure(figsize=(8, 8))
plt.pie([ecore_total, pcore_total], 
        labels=['E-cores', 'P-cores'],
        colors=['blue', 'red'],
        autopct='%1.1f%%',
        startangle=90)
plt.title('Core Type Usage Distribution')
```

## Troubleshooting

### Issue 1: Premature P-core Activation
```python
# Check if P-cores activate too early
first_pcore_event = parking_df[parking_df['PerformanceCoresUnparkedCount'] > 0].iloc[0]
if first_pcore_event['EfficiencyCoresUnparkedCount'] < 6:  # Assuming 8 E-cores total
    print("WARNING: P-cores activated before E-cores fully utilized")
```

### Issue 2: Excessive Total Cores
```python
# Check if too many cores unparked for workload
max_cores = parking_df['TotalCoresUnparkedCount'].max()
avg_cores = parking_df['TotalCoresUnparkedCount'].mean()
if avg_cores > max_cores * 0.7:
    print("INFO: Consistently high core count (heavy workload or poor parking)")
```

### Issue 3: Oscillation
```python
# Detect rapid changes
changes = parking_df['TotalCoresUnparkedCount'].diff().abs()
rapid_changes = changes[changes >= 2]
if len(rapid_changes) > len(parking_df) * 0.3:
    print("WARNING: Excessive parking oscillation detected")
```

## Related Analyses
- **WPS Containment Unpark**: Sets unpark targets
- **Hetero Response**: Thread utility drives parking decisions
- **CPU Utilization**: Validates parking decisions are correct
- **Power States**: Parked cores can enter deeper C-states
