# EPO Changes Module

## Overview
Tracks Energy Performance Optimization (EPO) setting changes from the DPTF (Dynamic Platform and Thermal Framework) to understand power policy adjustments during trace.

## Analysis Type
**Power Policy Configuration Tracking**

## What It Extracts
- EPO parameter GUIDs (power scheme identifiers)
- Parameter values (power settings)
- Timestamp of policy changes
- Power source transitions (AC vs battery)

## Data Source

### ETW Provider:
- **Provider**: `EsifUmdf2EtwProvider`
- **Event Level**: `win:Info`
- **Message Pattern**: `"Setting power scheme for power source"`

### Extracted Fields:
```python
event["Message"]  # Contains GUID and value
# Example: "Setting power scheme for power source; param GUID = 
8619B916-E004-4DD8-9B66-DAE86F806698; param Value = 1"
```

## Output Format
```python
{
    'timestamp': [0.123, 1.456, ...],
    'param': ['8619B916-E004-4DD8-9B66-DAE86F806698', ...],  # Power setting GUID
    'value': ['1', '0', '2', ...]  # Setting value
}
```

## Common GUIDs

### Example Power Settings:
- Processor performance boost mode
- Max/min processor state
- System cooling policy
- Display brightness
- Sleep/hibernate timers

*Note: Specific GUID meanings are platform and Windows version dependent*

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `EPOChanges()`
- **Lines**: Approximately 1148-1185

## Common Analyses

### 1. Policy Change Frequency
```python
# Count how often settings change
change_count = len(epo_df)
print(f"EPO changes during trace: {change_count}")
```

### 2. Identify Unstable Settings
```python
# Find settings that change frequently
param_counts = epo_df['param'].value_counts()
unstable = param_counts[param_counts > 5]
```

### 3. Timeline of Changes
```python
# Plot when power settings changed
plt.scatter(epo_df['timestamp'], epo_df['value'].astype(int))
```

## Use Cases
- Understand power policy transitions
- Identify AC/battery power source switches
- Correlate policy changes with performance issues
- Debug power management behavior

## Integration
- Compare with **CPU Frequency** to see frequency scaling response
- Correlate with **WLC** workload classification changes
- Check against **PPM Settings** for overall power strategy

## Related Analyses
- PPM Settings, CPU Frequency, WLC, Power States
