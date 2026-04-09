# Containment Policy Change Module

## Overview
Tracks changes to the processor containment policy during trace execution, showing when the scheduler enables/disables core parking containment.

## Analysis Type
**Core Parking Policy Tracking**

## What It Extracts
- Containment policy state changes (enabled/disabled)
- Timestamp of policy transitions
- Reason codes for policy changes
- Impact on core parking behavior

## Data Source

### ETW Provider:
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Event**: `ContainmentPolicyChange`

### Extracted Fields:
```python
- ContainmentEnabled: Boolean (0=disabled, 1=enabled)
- Timestamp: Event occurrence time
- Reason: Why policy changed (if available)
```

## Output Format
```python
{
    'timestamp': [0.123, 1.456, ...],
    'ContainmentEnabled': [True, False, True, ...],
    'TransitionCount': [1, 2, 3, ...]  # Derived
}
```

## Containment Policy States

### Enabled (ContainmentEnabled=1):
- Scheduler restricts unparking to specific cores
- Attempts to keep workload on minimal cores
- Better power efficiency
- May limit parallelism

### Disabled (ContainmentEnabled=0):
- Scheduler can unpark any available cores
- Maximum parallelism available
- Higher power consumption
- Better burst performance

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `ContainmentPolicychange()`
- **Lines**: Approximately 1350-1380

## Common Analyses

### 1. Policy Stability
```python
# Check if policy is stable or toggling
transition_count = len(containment_df)
print(f"Policy changed {transition_count} times")
```

### 2. Time in Each State
```python
# Calculate duration in enabled vs disabled
enabled_time = containment_df[containment_df['ContainmentEnabled']==True]['duration'].sum()
disabled_time = containment_df[containment_df['ContainmentEnabled']==False]['duration'].sum()
```

### 3. Correlate with Workload
```python
# See if policy changes match workload intensity
# (merge with WLC or CPU utilization data)
```

## Typical Behavior

### Light Workload:
- Policy typically enabled
- Few cores active
- Maximizes power savings

### Moderate Workload:
- Policy may toggle
- System balances performance vs power
- Adaptive behavior

### Heavy Workload:
- Policy typically disabled
- All cores available
- Maximum parallelism

## Use Cases
- Understand scheduler core parking decisions
- Debug performance issues (is containment limiting parallelism?)
- Analyze power vs performance tradeoffs
- Validate adaptive behavior matches expectations

## Integration
- Correlate with **WPS Containment Unpark** for unpark count impact
- Compare with **WLC** for workload-based policy changes
- Check against **CPU Utilization** for performance impact
- Review with **Hetero Parking** for core type selection

## Troubleshooting

### Issue: Performance Limited
```python
# Check if containment is preventing core usage
if containment_df['ContainmentEnabled'].iloc[-1]:
    print("WARNING: Containment enabled - may limit parallelism")
```

### Issue: High Power Consumption
```python
# Check if containment is disabled when it should be enabled
if not containment_df['ContainmentEnabled'].iloc[-1]:
    print("INFO: Containment disabled - more cores available")
```

## Related Analyses
- WPS Containment Unpark, Hetero Parking, WLC, CPU Utilization, PPM Settings
