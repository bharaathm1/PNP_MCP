# PPM Settings Validation Constraints Reference

## Overview
Comprehensive validation constraints for Power Performance Manager (PPM) parameter settings. Contains **179 individual constraint checks** that validate PPM configuration values against expected baseline.

## Purpose
Automated validation that all PPM settings (performance thresholds, timing parameters, boost modes, parking policies, etc.) are configured correctly for power-optimized workloads.

## Constraint Structure

Each constraint validates a single PPM setting:
```
CONSTRAINT(
    NAME="(ParameterName_PowerMode_CoreType) settings",
    CATEGORY="SOCWatch",
    CONDITION=NOT(SOCWATCH_VALUE("ParameterName") == ExpectedValue),
    MESSAGE="checking for ParameterName settings",
    AR="settings are not matching to expected value"
)
```

## Naming Convention

PPM parameters follow this pattern:
```
<Profile>_<Parameter>_<PowerMode>_<CoreType>
```

### Components:
- **Profile**: `Default`, `Balanced`, `HighPerf`, `PowerSaver`
- **Parameter**: Setting name (e.g., `PerfDecreaseTime`, `PerfIncreaseTime`)
- **PowerMode**: 
  - `DC` = Battery (DC power)
  - `AC` = Plugged in (AC power)
- **CoreType**:
  - `0` = P-cores (Performance cores)
  - `1` = E-cores (Efficiency cores)

### Example:
`Default_PerfDecreaseTime_DC_0` = Default profile, Performance decrease time, Battery mode, P-cores

## Parameter Categories

### 1. Performance Timing Parameters

#### PerfDecreaseTime
Controls how quickly processor performance decreases when demand drops.

| Parameter | Expected Value | Unit |
|-----------|---------------|------|
| `PerfDecreaseTime_DC_0` | 1 | Time units |
| `PerfDecreaseTime_AC_0` | 1 | Time units |
| `PerfDecreaseTime_DC_1` | 2 | Time units |
| `PerfDecreaseTime_AC_1` | 2 | Time units |

**Interpretation**: Lower values = faster frequency reduction when load decreases

#### PerfIncreaseTime
Controls how quickly processor performance increases when demand rises.

| Parameter | Expected Value | Unit |
|-----------|---------------|------|
| `PerfIncreaseTime_DC_0` | 1 | Time units |
| `PerfIncreaseTime_AC_0` | 1 | Time units |
| `PerfIncreaseTime_DC_1` | 1 | Time units |
| `PerfIncreaseTime_AC_1` | 1 | Time units |

**Interpretation**: Lower values = faster frequency increase when load increases

### 2. Performance Policy Parameters

#### PerfDecreasePolicy
Algorithm used to decrease processor performance.

| Parameter | Expected Value | Policy Type |
|-----------|---------------|-------------|
| `PerfDecreasePolicy_DC_0` | 0 | Algorithm 0 |
| `PerfDecreasePolicy_AC_0` | 0 | Algorithm 0 |
| `PerfDecreasePolicy_DC_1` | 0 | Algorithm 0 |
| `PerfDecreasePolicy_AC_1` | 0 | Algorithm 0 |

**Policy Types**:
- `0` = Ideal (smoothest transitions)
- `1` = Single (immediate)
- `2` = Rocket (aggressive)

#### PerfIncreasePolicy
Algorithm used to increase processor performance.

| Parameter | Expected Value | Policy Type |
|-----------|---------------|-------------|
| `PerfIncreasePolicy_DC_0` | 0 | Algorithm 0 |
| `PerfIncreasePolicy_AC_0` | 0 | Algorithm 0 |
| `PerfIncreasePolicy_DC_1` | 3 | Algorithm 3 |
| `PerfIncreasePolicy_AC_1` | 3 | Algorithm 3 |

**Note**: E-cores (type 1) use different policy (3) than P-cores (0)

### 3. Performance Threshold Parameters

#### PerfDecreaseThreshold
Utilization threshold below which performance is decreased.

| Parameter | Expected Value | Threshold |
|-----------|---------------|-----------|
| `PerfDecreaseThreshold_DC_0` | 20 | 20% |
| `PerfDecreaseThreshold_AC_0` | 30 | 30% |
| `PerfDecreaseThreshold_DC_1` | 20 | 20% |
| `PerfDecreaseThreshold_AC_1` | 30 | 30% |

**Interpretation**: 
- DC (battery): More aggressive (20%) to save power
- AC (plugged): Less aggressive (30%) for better responsiveness

#### PerfIncreaseThreshold
Utilization threshold above which performance is increased.

| Parameter | Expected Value | Threshold |
|-----------|---------------|-----------|
| `PerfIncreaseThreshold_DC_0` | 50 | 50% |
| `PerfIncreaseThreshold_AC_0` | 60 | 60% |
| `PerfIncreaseThreshold_DC_1` | 50 | 50% |
| `PerfIncreaseThreshold_AC_1` | 60 | 60% |

### 4. Min/Max Policy Parameters

#### PerfMinPolicy
Minimum performance level allowed.

| Parameter | Expected Value | Min % |
|-----------|---------------|-------|
| `PerfMinPolicy_DC_0` | 5 | 5% |
| `PerfMinPolicy_AC_0` | 5 | 5% |
| `PerfMinPolicy_DC_1` | 5 | 5% |
| `PerfMinPolicy_AC_1` | 5 | 5% |

**Interpretation**: Cores can scale down to 5% of max frequency

#### PerfTimeCheck
Time interval to check performance adjustments.

| Parameter | Expected Value | Interval |
|-----------|---------------|----------|
| `PerfTimeCheck_DC_0` | 30 | 30ms |
| `PerfTimeCheck_AC_0` | 30 | 30ms |
| `PerfTimeCheck_DC_1` | 30 | 30ms |
| `PerfTimeCheck_AC_1` | 30 | 30ms |

### 5. Boost Mode Parameters

#### PerfBoostMode
Turbo boost behavior configuration.

| Value | Mode | Description |
|-------|------|-------------|
| 0 | Disabled | No turbo boost |
| 1 | Enabled | Standard turbo |
| 2 | Aggressive | Maximum performance |
| 3 | Efficient Enabled | Balanced boost |
| 4 | Efficient Aggressive | Aggressive efficient |
| 5 | Aggressive At Guaranteed | Boost at guaranteed frequency |
| 6 | Efficient Aggressive At Guaranteed | Efficient boost at guaranteed |

#### PerfBoostPolicy
Boost policy selection.

| Value | Policy | Description |
|-------|--------|-------------|
| 0-100 | Percentage | Boost aggressiveness |

### 6. Autonomous Mode Parameters

#### PerfAutonomousMode
Hardware-controlled frequency scaling.

| Value | Mode | Description |
|-------|------|-------------|
| 0 | Disabled | OS controls frequency |
| 1 | Enabled | Hardware controls frequency |

**Interpretation**: Autonomous mode allows hardware to adjust frequency faster than OS

#### PerfAutonomousWindow
Time window for autonomous decisions.

Expected values vary by configuration (typically 0-100 time units)

### 7. Hetero Parameters

#### HeteroDecreaseThreshold
Threshold for demoting threads from P-cores to E-cores.

Expected values: 10-40% depending on profile

#### HeteroIncreaseThreshold
Threshold for promoting threads from E-cores to P-cores.

Expected values: 50-90% depending on profile

#### HeteroClass1FloorPerf / HeteroClass0FloorPerf
Minimum performance levels for each core type.

- Class 0 = P-cores
- Class 1 = E-cores

### 8. EPP (Energy Performance Preference) Parameters

#### EnergyPerfPreference
OS hint for hardware performance/power tradeoff.

| Value | Preference | Description |
|-------|-----------|-------------|
| 0 | Performance | Maximum performance |
| 50 | Balanced | Balance performance/power |
| 100 | Power Saver | Maximum power savings |
| 128 | Default | Platform default |

### 9. Parking Parameters

#### ParkingPerfState
Performance state when cores are parked.

Expected values: 0-100 (percentage of max frequency)

#### AllowScaling
Allow frequency scaling when parked.

| Value | Behavior |
|-------|----------|
| 0 | No scaling |
| 1 | Allow scaling |

## Common Parameter Patterns

### DC vs AC Differences
Most parameters have different values for battery (DC) vs plugged in (AC):
- **DC**: More aggressive power saving (lower thresholds, faster decrease)
- **AC**: More responsive performance (higher thresholds, faster increase)

### P-core vs E-core Differences
Core type 0 (P-cores) vs type 1 (E-cores) often have different settings:
- **P-cores**: Optimized for burst performance
- **E-cores**: Optimized for sustained efficiency

## Validation Process

```
Read PPM Settings from ETL
    ↓
For each of 179 parameters:
    ↓
    Compare actual vs expected
    ↓
    If mismatch:
        ↓
        Report failure
        ↓
        AR: "settings are not matching to expected value"
    ↓
Generate validation report
    ↓
Summary: X/179 constraints passed
```

## Usage Example

### Check Specific Parameter
```python
# Example: Check PerfDecreaseTime for P-cores on battery
ppm_settings = trace.PPMsettingRundown()

decrease_time_dc_0 = ppm_settings[
    ppm_settings['PPM'] == 'Default_PerfDecreaseTime_DC_0'
]['value'].values[0]

expected = 1
if decrease_time_dc_0 != expected:
    print(f"FAIL: Expected {expected}, got {decrease_time_dc_0}")
```

### Validate All Settings
```python
# Load expected values from constraint file
expected_values = load_constraints("PPM_VAL_constraints.txt")

# Get actual values from trace
actual_values = trace.PPMsettingRundown()

# Compare
failures = []
for param, expected in expected_values.items():
    actual = actual_values[actual_values['PPM'] == param]['value'].values[0]
    if actual != expected:
        failures.append((param, expected, actual))

print(f"Passed: {179 - len(failures)}/179")
for param, exp, act in failures:
    print(f"FAIL: {param} - Expected: {exp}, Actual: {act}")
```

## Common Failure Scenarios

### Wrong Power Profile
If many parameters fail validation, system may be using wrong power profile:
- Check active profile: Balanced / High Performance / Power Saver
- Verify profile matches test requirements

### Platform Differences
Some parameters may vary by platform generation:
- Alder Lake vs Raptor Lake vs Meteor Lake
- Different default values expected

### BIOS Settings
Some parameters controlled by BIOS/firmware:
- SpeedStep settings
- Turbo boost enable/disable
- Core parking policy

### Custom Power Plan
User or OEM may have customized power plan:
- Check Windows Power Options
- Verify plan matches baseline configuration

## Related Constraints
- [PPM Constraints](constraints_ppm.md) - High-level PPM validation
- [Teams Constraints](constraints_teams.md) - Teams workload-specific validation
- [Constraints Validation](constraints_validation.md) - General constraint framework

## Related Analyses
- PPM Settings - Extract actual PPM configuration
- CPU Frequency - Verify frequency scaling behavior
- Hetero Response - Validate hetero scheduling
- WLC - Check workload classification alignment

## Implementation Location
- **Constraint File**: `speedlibs_service/constraints/PPM_VAL_constraints.txt`
- **Total Constraints**: 179
- **Validation Module**: Part of ETL analysis comprehensive validation
- **Related Code**: `speedlibs_service/speedlibs_clean.py` - PPMsettingRundown()

## Quick Reference: Most Critical Parameters

| Parameter | Expected (DC) | Expected (AC) | Impact If Wrong |
|-----------|--------------|---------------|-----------------|
| PerfBoostMode | Varies | Varies | Performance/power tradeoff |
| PerfIncreaseThreshold_0 | 50 | 60 | Responsiveness |
| PerfDecreaseThreshold_0 | 20 | 30 | Power savings |
| HeteroIncreaseThreshold | 50-90 | 50-90 | Thread migration timing |
| EnergyPerfPreference | 50-100 | 0-50 | Hardware behavior |

## Debugging Tips

### Issue: Many Failures
```python
# Check if using correct power profile
active_profile = ppm_df['profileid'].iloc[0]
print(f"Active profile: {active_profile}")
# Should match expected baseline (usually "Balanced")
```

### Issue: Single Parameter Fails
```python
# Check if parameter exists in trace
param_name = "Default_PerfDecreaseTime_DC_0"
if param_name in ppm_df['PPM'].values:
    value = ppm_df[ppm_df['PPM']==param_name]['value'].values[0]
    print(f"{param_name} = {value}")
else:
    print(f"{param_name} not found in trace")
```

### Issue: Platform-Specific
```python
# Some platforms may have different expected values
# Check platform generation and adjust expected values
platform_info = get_platform_info()
if platform_info['generation'] == 'ADL':
    # Alder Lake expected values
elif platform_info['generation'] == 'MTL':
    # Meteor Lake expected values
```

## Status Indicators

- ✅ **PASS (179/179)**: All PPM settings match expected configuration
- ⚠️ **PARTIAL (150+/179)**: Most settings correct, some mismatches
- ❌ **FAIL (<150/179)**: Many settings incorrect, check power profile

## Notes

1. This constraint file is the most comprehensive with 179 individual checks
2. Expected values represent baseline power-optimized configuration
3. Some platform variations are normal and acceptable
4. Focus on critical parameters (boost, thresholds, hetero) first
5. Full validation ensures consistent power measurement environment
