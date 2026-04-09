# PPM Settings Module

## Overview
Extracts Power Performance Manager (PPM) configuration settings from trace, showing the baseline power management policy and any runtime changes.

## Analysis Type
**Power Management Configuration Analysis**

## What It Extracts
- PPM parameter names and values at trace start (rundown)
- PPM setting changes during trace execution
- Profile IDs and profile names (Balanced, High Performance, Power Saver)
- Setting types and classes (processor, disk, display, etc.)

## Data Source

### Two Related Methods:

#### 1. PPMsettingRundown()
Captures baseline PPM settings at trace start

**ETW Events**:
- `Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown`
- `Microsoft-Windows-Kernel-Processor-Power/ProfileRundown`

**Fields**:
- Name: PPM parameter name
- Value: Current setting value
- ProfileId: Active power profile
- Class: Setting category
- Type: Data type

#### 2. PPMsettingschange()
Tracks PPM setting changes during trace

**ETW Events**:
- `Microsoft-Windows-Kernel-Processor-Power/ProfileSettingsChange`

**Fields**:
- Same as rundown, plus change timestamp

## Output Format

### PPM Settings Rundown:
```python
{
    'timestamp': [0.0, 0.0, ...],
    'PPM': ['PERFBOOSTMODE', 'PERFBOOSTPOL', 'PROCTHROTTLEMAX', ...],
    'value': [2, 100, 100, ...],
    'profileid': ['Balanced', 'Balanced', ...],
    'ValueSize': [4, 4, ...],
    'Type': [1, 1, ...],
    'Class': [0, 0, ...]
}
```

## Common PPM Parameters

| Parameter | Description | Typical Values |
|-----------|-------------|----------------|
| `PERFBOOSTMODE` | Processor boost mode | 0=Disabled, 1=Enabled, 2=Aggressive, 3=Efficient |
| `PROCTHROTTLEMAX` | Max processor state | 0-100 (percentage) |
| `PROCTHROTTLEMIN` | Min processor state | 0-100 (percentage) |
| `HETEROCLASS1FLOORPERF` | E-core performance floor | 0-100 |
| `HETERODECREASETHRESHOLD` | Hetero demotion threshold | 0-100 |
| `HETEROINCREASETHRESHOLD` | Hetero promotion threshold | 0-100 |

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `PPMsettingRundown()`, `PPMsettingschange()`
- **Lines**: Approximately 1185-1350

## Common Analyses

### 1. Check Active Power Profile
```python
active_profile = ppm_df['profileid'].iloc[0]
print(f\"Active profile: {active_profile}\")
```

### 2. Review Performance Settings
```python
boost_mode = ppm_df[ppm_df['PPM'] == 'PERFBOOSTMODE']['value'].values[0]
max_proc = ppm_df[ppm_df['PPM'] == 'PROCTHROTTLEMAX']['value'].values[0]
print(f\"Boost mode: {boost_mode}, Max CPU: {max_proc}%\")
```

### 3. Hetero Policy Settings
```python
hetero_settings = ppm_df[ppm_df['PPM'].str.contains('HETERO')]
```

### 4. Identify Setting Changes
```python
# Compare rundown vs changes
changes_df = ppm_changes_df  # From PPMsettingschange()
changed_params = changes_df['PPM'].unique()
```

## Power Profiles

### Balanced (Default):
- Moderate performance
- Dynamic frequency scaling
- Balanced P-core/E-core usage

### High Performance:
- Maximum performance
- Higher frequency targets
- Aggressive turbo boost
- More P-core usage

### Power Saver:
- Minimize power consumption
- Lower frequency caps
- Prefer E-cores
- Slower response times

## Use Cases
- Understand why system behaves certain way
- Debug unexpected performance issues
- Validate power policy is as expected
- Compare different power profiles

## Integration
- Correlate with **CPU Frequency** to see policy impact
- Check against **Hetero Response** for promotion thresholds
- Compare with **WLC** for workload-based adjustments
- Validate with **Containment** settings

## Troubleshooting

### Issue: Poor Performance
```python
# Check if CPU is throttled
max_proc = ppm_df[ppm_df['PPM']=='PROCTHROTTLEMAX']['value'].values[0]
if max_proc < 100:
    print(f\"WARNING: CPU capped at {max_proc}%\")
```

### Issue: High Power Consumption
```python
# Check if boost mode is too aggressive
boost = ppm_df[ppm_df['PPM']=='PERFBOOSTMODE']['value'].values[0]
if boost >= 2:
    print(\"INFO: Aggressive boost mode enabled\")
```

## Related Analyses
- CPU Frequency, Hetero Response, WLC, EPO Changes, Containment Policy
