# Hetero Response Module

## Overview
Extracts and analyzes heterogeneous response data that tracks how the scheduler promotes/demotes threads between Performance (P-cores) and Efficiency (E-cores) on hybrid CPU architectures.

## Analysis Type
**Hybrid Architecture Thread Scheduling Analysis**

## What It Tracks
- Thread promotion from E-cores to P-cores
- Thread demotion from P-cores to E-cores  
- Estimated vs Actual utility of threads
- Active time tracking
- Scheduler decision patterns

## Data Source

### ETW Provider:
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Event**: `HeteroResponse`
- **Event Level**: `win:Info`

### Event Fields:
```python
event["TimeStamp"]          # Event time (microseconds)
event["EstimatedUtility"]  # Predicted thread utility (array)
event["ActualUtility"]     # Measured thread utility (array)
event["ActiveTime"]         # Thread active time
event["Decision"]           # Scheduler decision bit
```

## Extraction Process

### Step 1: Get Hetero Events
```python
event_type_list = [
    "Microsoft-Windows-Kernel-Processor-Power/HeteroResponse/win:Info"
]
events = trace.get_events(
    event_types=event_type_list,
    time_range=trace.time_range
)
```

### Step 2: Extract Utility Metrics
```python
for event in events:
    timestamp.append(event["TimeStamp"] / 1000000)  # Convert to ms
    ET.append(max(event["EstimatedUtility"]))       # Max estimated
    AT.append(max(event["ActualUtility"]))          # Max actual
    Active_time.append(event["ActiveTime"])
    decisionBit.append(event["Decision"])
```

### Step 3: Create DataFrame
```python
df = pd.DataFrame({
    "timestamp": timestamp,
    "EstimatedUtility": ET,
    "ActualUtility": AT,
    "ActiveTime": Active_time,
    "decision": decisionBit
})
```

## Output Format

### DataFrame Structure:
```python
{
    'timestamp': [0.123, 0.456, ...],         # Milliseconds
    'EstimatedUtility': [75, 82, 90, ...],    # 0-100 scale
    'ActualUtility': [70, 85, 88, ...],       # 0-100 scale
    'ActiveTime': [1234, 2456, ...],          # Microseconds
    'decision': [0, 1, 0, ...]                # 0=demote, 1=promote
}
```

## Key Metrics

### 1. Estimated Utility
- **Range**: 0-100
- **Meaning**: Scheduler's prediction of thread importance
- **High (>80)**: Thread needs P-core
- **Medium (50-80)**: Thread can use either
- **Low (<50)**: Thread should use E-core

### 2. Actual Utility
- **Range**: 0-100
- **Meaning**: Measured thread utility after execution
- **Purpose**: Validate scheduler predictions
- **Accuracy**: Compare to EstimatedUtility

### 3. Decision Bit
- **0**: Demote to E-core (or keep on E-core)
- **1**: Promote to P-core (or keep on P-core)

### 4. Active Time
- **Unit**: Microseconds
- **Meaning**: Thread execution time
- **Use**: Calculate utilization impact

## Analysis Patterns

### 1. Promotion Delay
```python
# Time from high estimated utility to promotion
promotions = df[df['decision'] == 1]
promotion_delays = promotions['timestamp'].diff()
avg_delay = promotion_delays.mean()
print(f"Average promotion delay: {avg_delay:.2f} ms")
```

### 2. Prediction Accuracy
```python
# Compare estimated vs actual utility
df['prediction_error'] = abs(
    df['EstimatedUtility'] - df['ActualUtility']
)
avg_error = df['prediction_error'].mean()
print(f"Average prediction error: {avg_error:.1f}%")
```

### 3. Promotion Rate
```python
# Percentage of events that are promotions
promotion_rate = (df['decision'] == 1).sum() / len(df) * 100
print(f"Promotion rate: {promotion_rate:.1f}%")
```

### 4. Utility Distribution
```python
# Histogram of estimated utilities
import matplotlib.pyplot as plt
plt.hist(df['EstimatedUtility'], bins=20)
plt.xlabel('Estimated Utility')
plt.ylabel('Frequency')
plt.title('Thread Utility Distribution')
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `EtlTrace`
- **Method**: `heteroresponse()`
- **Lines**: Approximately 723-758

## Usage Patterns

### Standalone Usage:
```python
from speedlibs_clean import EtlTrace

# Create trace object
etl_trace = EtlTrace(trace_obj)

# Extract hetero response data
hetero_df = etl_trace.heteroresponse()

# Analyze scheduler behavior
promotions = hetero_df[hetero_df['decision'] == 1]
print(f"Total promotions: {len(promotions)}")
print(f"Avg estimated utility: {hetero_df['EstimatedUtility'].mean():.1f}")
```

### Via Comprehensive Analysis:
```python
result = generate_comprehensive_analysis(
    etl_path="path/to/trace.etl",
    include_hetero=True
)

# Access hetero response data
hetero_df = pd.DataFrame(result['hetero_response'])
```

## Interpretation Guide

### Good Hetero Response:
```
Promotion delay: <20ms average
Prediction accuracy: <15% error
Promotion rate: 20-40% (balanced)
Utility distribution: Matches workload
```

### Poor Hetero Response:
```
Promotion delay: >50ms (slow response)
Prediction accuracy: >30% error (bad predictions)
Promotion rate: >70% (over-promotes) or <10% (under-promotes)
Utility distribution: Doesn't match actual workload
```

## Common Issues

### Issue 1: Slow Promotions
```python
# Check for delayed promotions
high_utility = df[df['EstimatedUtility'] > 80]
if len(high_utility) > 0:
    promoted = high_utility[high_utility['decision'] == 1]
    delay = len(high_utility) - len(promoted)
    if delay > len(high_utility) * 0.3:  # >30% not promoted
        print("WARNING: Slow promotion response")
```

### Issue 2: Prediction Errors
```python
# Find significant prediction errors
large_errors = df[df['prediction_error'] > 30]
if len(large_errors) > len(df) * 0.2:  # >20% have large errors
    print("WARNING: Poor utility prediction")
```

### Issue 3: Excessive Promotions
```python
# Check for over-promotion
low_utility_promotions = df[
    (df['EstimatedUtility'] < 50) & (df['decision'] == 1)
]
if len(low_utility_promotions) > 0:
    print(f"WARNING: {len(low_utility_promotions)} low-utility promotions")
```

## Performance Implications

### Optimal Behavior:
- **Fast promotions**: High-utility threads quickly moved to P-cores
- **Accurate predictions**: EstimatedUtility matches ActualUtility
- **Balanced decisions**: Not too aggressive or too conservative

### Performance Impact:
- **Slow promotions**: Interactive threads lag on E-cores → user-visible delay
- **Over-promotion**: P-cores saturated → power inefficiency
- **Under-promotion**: Performance threads stuck on E-cores → throughput loss

## Integration with Other Analyses

### With Containment Breach:
```python
# Hetero response should prevent containment breaches
# If breaches occur despite promotions, scheduler is failing
```

### With CPU Utilization:
```python
# High P-core utilization + low promotion rate = under-utilizing P-cores
# Low E-core utilization + high promotion rate = over-promoting
```

### With WLC:
```python
# Workload classification should influence hetero decisions
# Heavy WLC state should correlate with high promotion rate
```

## Visualization Recommendations

### Timeline Plot:
```python
import matplotlib.pyplot as plt

plt.figure(figsize=(12, 6))
plt.plot(hetero_df['timestamp'], hetero_df['EstimatedUtility'], 
         label='Estimated', alpha=0.7)
plt.plot(hetero_df['timestamp'], hetero_df['ActualUtility'], 
         label='Actual', alpha=0.7)
plt.scatter(hetero_df[hetero_df['decision']==1]['timestamp'],
            hetero_df[hetero_df['decision']==1]['EstimatedUtility'],
            color='red', label='Promotions', s=10)
plt.xlabel('Time (ms)')
plt.ylabel('Utility')
plt.title('Hetero Response: Utility and Promotions')
plt.legend()
```

## Related Analyses
- **Containment Breach**: Validates hetero response effectiveness
- **CPU Utilization**: Shows P-core vs E-core usage patterns
- **Thread Statistics**: Tracks individual thread behavior
- **PPM Validation**: Power management policy compliance
