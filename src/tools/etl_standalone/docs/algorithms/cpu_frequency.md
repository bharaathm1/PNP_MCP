# CPU Frequency Analysis Module

## Overview
Extracts and analyzes CPU frequency data per core to understand frequency scaling patterns, turbo boost behavior, and power management effectiveness.

## Analysis Type
**CPU Frequency Scaling and Performance Analysis**

## What It Extracts
- Per-core frequency over time
- Frequency scaling patterns (P-cores vs E-cores)
- Turbo boost utilization
- Frequency throttling events
- P-state transitions

## Data Source

### ETW Provider:
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Event**: `PStateChange` or similar frequency events
- **Additional**: Performance counter data

### Frequency Metrics:
- **Current Frequency**: Real-time frequency per core
- **Min/Max/Avg**: Statistical summary per core
- **Frequency Range**: Operating range for each core type

## Extraction Process

### Method: `get_cpu_freq()`
Located in: `speedlibs_service/speedlibs_clean.py`

```python
def get_cpu_freq(self):
    """
    CPU frequency data - per-core processing
    Returns DataFrame with frequency stats per logical CPU
    """
    # Extract frequency events from trace
    # Process per-core frequency data
    # Calculate min/max/avg statistics
    # Return DataFrame with frequency metrics
```

## Output Format

### DataFrame Structure:
```python
{
    'CPU': [0, 1, 2, 3, ...],           # Logical CPU number
    'Min_Freq_MHz': [800, 800, ...],     # Minimum frequency
    'Max_Freq_MHz': [5200, 5200, ...],   # Maximum frequency  
    'Avg_Freq_MHz': [2800, 3100, ...],   # Average frequency
    'Samples': [1234, 1456, ...]         # Number of samples
}
```

## Typical Frequency Ranges

### Intel Processors:

| Core Type | Min Freq | Base Freq | Max Turbo |
|-----------|----------|-----------|-----------|
| **P-core (Performance)** | 800 MHz | 2.4-3.0 GHz | 4.5-5.8 GHz |
| **E-core (Efficiency)** | 800 MHz | 1.8-2.2 GHz | 3.0-4.0 GHz |

### AMD Processors:

| Core Type | Min Freq | Base Freq | Max Boost |
|-----------|----------|-----------|-----------|
| **Performance cores** | 550 MHz | 3.0-3.8 GHz | 4.5-5.7 GHz |

## Analysis Patterns

### 1. Frequency Scaling Effectiveness
```python
# Check if frequency scales with load
freq_range = freq_df['Max_Freq_MHz'] - freq_df['Min_Freq_MHz']
avg_range = freq_range.mean()

if avg_range < 500:
    print("WARNING: Limited frequency scaling")
elif avg_range > 3000:
    print("Good: Wide frequency scaling range")
```

### 2. Turbo Boost Utilization
```python
# Identify turbo boost usage
base_freq = 2400  # MHz, platform-specific
turbo_usage = freq_df[freq_df['Max_Freq_MHz'] > base_freq]
turbo_rate = len(turbo_usage) / len(freq_df) * 100
print(f"Turbo boost utilization: {turbo_rate:.1f}%")
```

### 3. P-core vs E-core Comparison
```python
# Assuming cores 0-3 are P-cores, 4-7 are E-cores
pcore_freq = freq_df[freq_df['CPU'] < 4]['Avg_Freq_MHz'].mean()
ecore_freq = freq_df[freq_df['CPU'] >= 4]['Avg_Freq_MHz'].mean()
print(f\"P-core avg: {pcore_freq:.0f} MHz\")
print(f\"E-core avg: {ecore_freq:.0f} MHz\")
print(f\"Frequency ratio: {pcore_freq/ecore_freq:.2f}x\")
```

### 4. Frequency Throttling Detection
```python
# Check for frequency capping
expected_max = 5200  # MHz, platform-specific
throttled = freq_df[freq_df['Max_Freq_MHz'] < expected_max * 0.8]
if len(throttled) > 0:
    print(f\"WARNING: {len(throttled)} cores show throttling\")
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `get_cpu_freq()`
- **Lines**: Approximately 931-980

## Usage Patterns

### Standalone Usage:
```python
from speedlibs_clean import EtlTrace

# Create trace object
etl_trace = EtlTrace(trace_obj)

# Extract frequency data
freq_df = etl_trace.get_cpu_freq()

# Analyze frequency scaling
for cpu in freq_df['CPU'].unique():
    cpu_data = freq_df[freq_df['CPU'] == cpu]
    print(f\"CPU {cpu}: {cpu_data['Min_Freq_MHz'].values[0]}-{cpu_data['Max_Freq_MHz'].values[0]} MHz\")
```

### Via Trace Summary:
```python
result = get_trace_summary(etl_path=\"path/to/trace.etl\")

# Access frequency stats
freq_df = result['summary_cpufrequencystats_df']
```

## Interpretation Guide

### Healthy Frequency Behavior:
```
✓ Wide frequency range (min to max turbo)
✓ P-cores reach higher frequencies than E-cores
✓ Frequency scales with utilization
✓ No unexpected throttling
```

### Problematic Patterns:
```
✗ Narrow frequency range (stuck near base)
✗ All cores at same frequency (no differentiation)
✗ Frequency doesn't match utilization
✗ Max frequency below expected turbo
```

## Common Issues

### Issue 1: Power Limit Throttling
```python
# All cores capped below max turbo
if freq_df['Max_Freq_MHz'].max() < expected_max_turbo:
    print(\"Possible power limit throttling (PL1/PL2)\")
```

### Issue 2: Thermal Throttling
```python
# Frequency drops during high utilization
# (Would need to correlate with utilization data)
print(\"Check for thermal throttling if max freq drops over time\")
```

### Issue 3: Fixed Frequency Mode
```python
# Min = Max (no scaling)
fixed = freq_df[freq_df['Min_Freq_MHz'] == freq_df['Max_Freq_MHz']]
if len(fixed) > 0:
    print(f\"WARNING: {len(fixed)} cores in fixed frequency mode\")
```

## Performance Implications

### High Frequency = Higher Performance:
- Faster instruction execution
- Lower latency
- Better interactive response

### High Frequency = Higher Power:
- More power consumption
- More heat generation  
- Reduced battery life

### Optimal Behavior:
- Scale up quickly for interactive workloads
- Scale down during idle/light load
- Use E-cores for background tasks
- Maximize P-core frequency for critical threads

## Integration with Other Analyses

### With CPU Utilization:
```python
# High utilization should correlate with high frequency
# Low utilization should allow low frequency
```

### With WLC (Workload Classification):
```python
# Heavy workload class should trigger high frequencies
# Light workload class should use low frequencies
```

### With Power States:
```python
# Deep C-states incompatible with high frequency
# Shallow C-states allow quick frequency scaling
```

### With Hetero Response:
```python
# Thread promotions to P-cores should increase frequency
# Demotions to E-cores should allow frequency reduction
```

## Visualization Recommendations

### Per-Core Frequency Heatmap:
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Pivot table for heatmap
freq_pivot = freq_df.pivot_table(
    index='CPU',
    values=['Min_Freq_MHz', 'Avg_Freq_MHz', 'Max_Freq_MHz']
)

sns.heatmap(freq_pivot, annot=True, fmt='.0f', cmap='YlOrRd')
plt.title('CPU Frequency Statistics (MHz)')
```

### Frequency Distribution:
```python
plt.figure(figsize=(10, 6))
plt.bar(freq_df['CPU'], freq_df['Avg_Freq_MHz'], alpha=0.7)
plt.xlabel('CPU Core')
plt.ylabel('Average Frequency (MHz)')
plt.title('Average Frequency per Core')
plt.axhline(y=base_freq, color='r', linestyle='--', label='Base Frequency')
```

## Platform-Specific Considerations

### Intel Hybrid (Alder Lake+):
- P-cores: 4.5-5.8 GHz turbo
- E-cores: 3.0-4.0 GHz max
- Clear differentiation expected

### AMD Zen (Ryzen):
- All cores similar frequency capability
- Boost algorithm per-core
- Less differentiation than Intel hybrid

### Older Platforms:
- May not report per-core frequency
- Turbo boost less aggressive
- Simpler frequency scaling

## Related Analyses
- **CPU Utilization**: Frequency should match load
- **Power States**: C-states affect frequency scaling
- **WLC**: Workload class influences frequency targets
- **Thermal Management**: Temperature limits max frequency
