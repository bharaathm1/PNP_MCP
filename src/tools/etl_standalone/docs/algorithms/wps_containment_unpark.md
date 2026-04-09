# WPS Containment Unpark Module

## Overview
Tracks Windows Power Scheduler (WPS) containment policy and core unparking decisions, showing how the scheduler balances Performance and Efficiency cores during workload changes.

## Analysis Type
**Hybrid CPU Core Parking and Containment Analysis**

## What It Tracks
- Containment policy enablement status
- P-core vs E-core unpark counts (before/after scheduler decisions)
- Crossover requirements (when workload needs P-cores)
- Raw target unpark counts
- Core parking transitions over time

## Data Source

### ETW Provider:
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Event**: `WpsContainmentUnparkCount`
- **Event Level**: `win:Info`

### Event Fields:
```python
event["TimeStamp"]                      # Event time (microseconds)
event["ContainmentEnabled"]             # Is containment policy active? (0/1)
event["ContainmentCrossOverRequired"]   # Does workload need P-cores? (0/1)
event["BeforeEfficientUnparkCount"]     # E-cores unparked before decision
event["AfterEfficientUnparkCount"]      # E-cores unparked after decision
event["BeforePerfUnparkCount"]          # P-cores unparked before decision
event["AfterPerfUnparkCount"]           # P-cores unparked after decision
event["RawTargetUnparkCount"]           # Scheduler's target unpark count
```

## Output Format

### DataFrame Structure:
```python
{
    'timestamp': [0.123, 0.456, ...],
    'ContainmentEnabled': [1, 1, 0, ...],          # 1=enabled, 0=disabled
    'ContainmentCrossOverRequired': [0, 1, ...],   # 1=needs P-cores
    'BeforeEfficientUnparkCount': [4, 4, 8, ...],
    'AfterEfficientUnparkCount': [4, 6, 8, ...],
    'BeforePerfUnparkCount': [0, 0, 2, ...],
    'AfterPerfUnparkCount': [0, 2, 4, ...],
    'RawTargetUnparkCount': [4, 8, 12, ...]
}
```

## Key Metrics

### 1. Containment Enabled
- **1**: Containment policy active (try to keep workload on E-cores)
- **0**: Containment disabled (use all available cores)

### 2. Crossover Required
- **0**: Workload can stay on E-cores
- **1**: Workload exceeds E-core capacity, needs P-cores

### 3. Unpark Counts
- **Before**: Core state before scheduler decision
- **After**: Core state after scheduler applies policy
- **Difference**: Shows scheduler's parking/unparking action

### 4. Raw Target
- Scheduler's calculated target for total unparked cores
- May differ from actual after policy constraints

## Analysis Patterns

### 1. Containment Effectiveness
```python
# Check if containment keeps workload on E-cores
containment_on = df[df['ContainmentEnabled'] == 1]
avg_pcore_use = containment_on['AfterPerfUnparkCount'].mean()
avg_ecore_use = containment_on['AfterEfficientUnparkCount'].mean()

print(f"With containment: {avg_ecore_use:.1f} E-cores, {avg_pcore_use:.1f} P-cores")
```

### 2. Crossover Events
```python
# Count how often workload needs P-cores
crossovers = df[df['ContainmentCrossOverRequired'] == 1]
crossover_rate = len(crossovers) / len(df) * 100
print(f"Crossover rate: {crossover_rate:.1f}%")
```

### 3. Parking Decisions
```python
# Track core parking/unparking
df['pcore_change'] = df['AfterPerfUnparkCount'] - df['BeforePerfUnparkCount']
df['ecore_change'] = df['AfterEfficientUnparkCount'] - df['BeforeEfficientUnparkCount']

unpark_events = df[df['pcore_change'] > 0]
park_events = df[df['pcore_change'] < 0]
print(f"P-core unpark events: {len(unpark_events)}")
print(f"P-core park events: {len(park_events)}")
```

### 4. Target vs Actual
```python
# Compare scheduler's target with actual result
df['total_actual'] = df['AfterPerfUnparkCount'] + df['AfterEfficientUnparkCount']
df['target_diff'] = df['RawTargetUnparkCount'] - df['total_actual']
print(f"Average deviation from target: {df['target_diff'].mean():.1f} cores")
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `wpscontainmentunpark()`
- **Lines**: Approximately 759-805

## Usage Patterns

### Standalone Usage:
```python
from speedlibs_clean import EtlTrace

etl_trace = EtlTrace(trace_obj)
wps_df = etl_trace.wpscontainmentunpark()

# Check containment behavior
print(f"Containment enabled: {(wps_df['ContainmentEnabled']==1).sum()} events")
print(f"Crossovers needed: {(wps_df['ContainmentCrossOverRequired']==1).sum()} events")
```

## Interpretation Guide

### Good Containment Behavior:
```
✓ Containment enabled when appropriate
✓ Low crossover rate (<20%) for light workloads
✓ Quick P-core unparking when crossover required
✓ E-cores saturated before P-cores used
```

### Poor Containment Behavior:
```
✗ Containment disabled unnecessarily (wastes power)
✗ High crossover rate (>50%) indicates over-containment
✗ Slow P-core response to crossover needs
✗ P-cores activated while E-cores idle
```

## Common Scenarios

### Scenario 1: Light Workload (Good)
```
ContainmentEnabled: 1
CrossoverRequired: 0
AfterEfficientUnparkCount: 4
AfterPerfUnparkCount: 0
→ Workload handled by E-cores, P-cores stay parked
```

### Scenario 2: Heavy Workload (Good)
```
ContainmentEnabled: 1
CrossoverRequired: 1
AfterEfficientUnparkCount: 8 (all E-cores)
AfterPerfUnparkCount: 4 (some P-cores)
→ E-cores maxed out, P-cores activated as needed
```

### Scenario 3: Performance Mode (Expected)
```
ContainmentEnabled: 0
CrossoverRequired: N/A
AfterPerfUnparkCount: High
→ Containment disabled, using all available cores
```

## Integration with Other Analyses

### With Hetero Parking Selection:
- WPS Containment decides IF cores should be unparked
- Hetero Parking Selection decides WHICH cores to unpark

### With CPU Utilization:
- High E-core utilization + no crossover = good containment
- Low E-core utilization + crossover = premature P-core activation

### With Hetero Response:
- Crossover events should trigger thread promotions
- P-core unparking should follow thread promotions

## Performance Implications

### Power Efficiency:
- More E-core usage = lower power consumption
- Fewer crossovers = better power efficiency
- Quick parking of P-cores saves power

### Performance:
- Delayed crossovers = performance loss
- Excessive containment = throughput throttling
- Proper balance = best power/performance

## Visualization Recommendations

### Timeline Plot:
```python
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

# Core unpark counts
ax1.plot(wps_df['timestamp'], wps_df['AfterEfficientUnparkCount'], 
         label='E-cores', color='blue')
ax1.plot(wps_df['timestamp'], wps_df['AfterPerfUnparkCount'], 
         label='P-cores', color='red')
ax1.fill_between(wps_df['timestamp'], 
                  wps_df[wps_df['ContainmentCrossOverRequired']==1]['AfterPerfUnparkCount'],
                  alpha=0.3, color='red', label='Crossover')
ax1.set_ylabel('Unparked Cores')
ax1.legend()
ax1.grid(True)

# Containment status
ax2.fill_between(wps_df['timestamp'], 
                  wps_df['ContainmentEnabled'], 
                  alpha=0.5, color='green', label='Containment Enabled')
ax2.set_xlabel('Time (ms)')
ax2.set_ylabel('Enabled')
ax2.set_ylim(-0.1, 1.1)
ax2.legend()
ax2.grid(True)
```

## Related Analyses
- **Hetero Parking Selection**: Decides which cores to unpark
- **Hetero Response**: Thread promotion triggers unpark decisions
- **CPU Utilization**: Shows actual core usage vs unpark status
- **Containment Breach**: Violations when containment fails
