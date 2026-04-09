# Containment Breach Analysis Logic

## Overview
Analyzes traces to identify "containment breaches" - situations where the system fails to execute a workload on the intended hardware resources (e.g., forced to use E-cores when P-cores were expected).

## Analysis Type
**PPM (Power Performance Manager) Behavior Analysis**

## What It Detects
- Workloads forced to inappropriate cores
- E-core utilization when P-cores should be used
- P-core starvation scenarios
- Containment policy violations
- Performance degradation patterns

## Core Concepts

### Containment Policy
The OS scheduler's strategy for placing threads on cores:
- **P-core First**: Performance-sensitive threads prefer P-cores
- **E-core Allowed**: Background threads can use E-cores
- **Hetero Response**: How quickly system promotes threads to P-cores

### Breach Scenarios

| Scenario | Description | Impact |
|----------|-------------|--------|
| **Forced E-core** | P-core thread forced to E-core | Performance loss |
| **P-core Starvation** | All P-cores busy, new threads wait | Latency increase |
| **Policy Violation** | Thread runs on unexpected core type | Unexpected behavior |
| **Hetero Delay** | Slow promotion from E to P-cores | User-visible lag |

## Analysis Process

### Step 1: Extract Thread Scheduling Events
```python
# Get context switch events
context_switches = trace.query("""
    SELECT 
        TimeStamp,
        ThreadId,
        NewThreadId,
        OldThreadPriority,
        NewThreadPriority,
        ProcessorNumber
    FROM Microsoft_Windows_Kernel_Process_CSwitch
""")
```

### Step 2: Identify Core Types
```python
# Classify processors as P-core or E-core
for proc_num in processors:
    core_type = get_processor_type(proc_num)
    core_map[proc_num] = core_type  # 'P' or 'E'
```

### Step 3: Track Thread Behavior
```python
for thread_id in high_priority_threads:
    # Track which cores thread ran on
    execution_history = get_thread_execution(thread_id)
    
    # Check for unexpected E-core usage
    if thread_should_use_pcores(thread_id):
        ecore_time = sum_time_on_ecores(execution_history)
        if ecore_time > threshold:
            record_breach(thread_id, ecore_time)
```

### Step 4: Calculate Breach Metrics
```python
breach_metrics = {
    'total_breaches': count_breaches(),
    'breach_duration': sum_breach_time(),
    'affected_threads': unique_threads_with_breaches(),
    'pcore_starvation_events': count_starvation(),
    'avg_hetero_delay': mean_promotion_delay()
}
```

## Key Metrics

### 1. Breach Count
- Total number of containment breach events
- Typically: 0 breaches is ideal
- Warning: >10 breaches may indicate issue

### 2. Breach Duration
- Total time threads spent on wrong core type
- Measured in milliseconds
- Typical: <1% of total execution time

### 3. P-core Starvation Count
- Number of times P-cores were fully saturated
- Indicates capacity constraints
- Typical: Should be rare in balanced workload

### 4. Hetero Response Delay
- Time from thread creation/wake to P-core assignment
- Ideal: <10ms for interactive threads
- Warning: >50ms causes user-visible lag

### 5. Policy Compliance Rate
```python
compliance_rate = (correct_placements / total_placements) * 100
# Target: >95% compliance
```

## Output Format

### DataFrame Structure:
```python
{
    'Timestamp': [event times...],
    'ThreadId': [thread IDs...],
    'ProcessName': [process names...],
    'BreachType': ['Forced E-core', 'P-core Starvation', ...],
    'Duration_ms': [breach durations...],
    'ExpectedCore': ['P', 'P', ...],
    'ActualCore': ['E', 'E', ...],
    'ProcessorNumber': [CPU numbers...],
    'Priority': [thread priorities...],
    'Impact': ['High', 'Medium', 'Low', ...]
}
```

### Summary Metrics:
```python
{
    'total_breaches': 15,
    'total_breach_time_ms': 234.5,
    'pcore_starvation_events': 5,
    'avg_hetero_delay_ms': 12.3,
    'worst_thread': 'Teams.exe:8472',
    'compliance_rate': 94.2
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `ContainmentBreachAnalyzer`
- **Method**: `analyze_containment_breach()`
- **Lines**: Approximately 1200-1500
- **Used By**: `generate_comprehensive_analysis()`

## Detection Algorithm

### High Priority Thread Identification:
```python
def identify_high_priority_threads(trace):
    # Priority > 12 typically needs P-cores
    high_pri_threads = trace.query("""
        SELECT DISTINCT ThreadId, Priority
        FROM ThreadInfo
        WHERE Priority >= 12
    """)
    return high_pri_threads
```

### Core Type Classification:
```python
def classify_processor(processor_number):
    # Based on processor topology
    if processor_number in pcore_list:
        return 'P'
    elif processor_number in ecore_list:
        return 'E'
    else:
        return 'Unknown'
```

### Breach Detection Logic:
```python
def detect_breach(thread_id, execution_events):
    breaches = []
    expected_core_type = get_expected_core_type(thread_id)
    
    for event in execution_events:
        actual_core_type = classify_processor(event.processor)
        
        if actual_core_type != expected_core_type:
            breach = {
                'timestamp': event.timestamp,
                'thread_id': thread_id,
                'expected': expected_core_type,
                'actual': actual_core_type,
                'duration_ms': event.duration
            }
            breaches.append(breach)
    
    return breaches
```

## Breach Classification

### Severity Levels:

| Severity | Condition | Example |
|----------|-----------|---------|
| **Critical** | Interactive thread >100ms on E-core | UI thread blocked |
| **High** | P-core thread >50ms on E-core | Render delay |
| **Medium** | P-core thread >10ms on E-core | Minor performance impact |
| **Low** | Brief E-core usage <10ms | Transitional state |

### Impact Assessment:
```python
def assess_impact(breach):
    if breach['duration_ms'] > 100:
        return 'Critical'
    elif breach['duration_ms'] > 50:
        return 'High'
    elif breach['duration_ms'] > 10:
        return 'Medium'
    else:
        return 'Low'
```

## Common Breach Patterns

### Pattern 1: Startup Burst
```
Scenario: Many threads spawn at once
Result: Temporary P-core saturation
Breaches: Short-duration E-core usage
Impact: Usually acceptable (transient)
```

### Pattern 2: Sustained Oversubscription
```
Scenario: More high-priority threads than P-cores
Result: Continuous breach events
Breaches: Long-duration E-core usage
Impact: Performance degradation
```

### Pattern 3: Hetero Policy Misconfiguration
```
Scenario: Policy doesn't promote threads fast enough
Result: Excessive E-core utilization
Breaches: Medium-duration breaches
Impact: User-visible lag
```

### Pattern 4: Priority Inversion
```
Scenario: Low priority thread blocks high priority
Result: High priority forced to E-core
Breaches: Variable duration
Impact: Can be severe
```

## Usage Patterns

### Standalone Analysis:
```python
from speedlibs_clean import ContainmentBreachAnalyzer

# Load trace
trace = load_trace_cached(etl_path)

# Analyze containment
analyzer = ContainmentBreachAnalyzer()
breach_df, summary = analyzer.analyze_containment_breach(
    trace,
    process_filter="Teams.exe"  # Optional: focus on specific process
)

# Check for critical breaches
critical = breach_df[breach_df['Impact'] == 'Critical']
print(f"Found {len(critical)} critical breaches")
```

### Via Comprehensive Analysis:
```python
result = generate_comprehensive_analysis(
    etl_path="path/to/trace.etl",
    include_containment=True
)

# Access containment data
breach_df = pd.DataFrame(result['containment_breach_data'])
summary = result['containment_summary']

print(f"Breach rate: {summary['compliance_rate']:.1f}%")
```

## Interpretation Guide

### Good Containment:
```
Total Breaches: 0-5
Breach Duration: <100ms total
P-core Starvation: 0-2 events
Compliance Rate: >98%
→ System properly placing threads
```

### Marginal Containment:
```
Total Breaches: 5-20
Breach Duration: 100-500ms total
P-core Starvation: 2-10 events
Compliance Rate: 95-98%
→ Some inefficiency, investigate high-count threads
```

### Poor Containment:
```
Total Breaches: >20
Breach Duration: >500ms total
P-core Starvation: >10 events
Compliance Rate: <95%
→ Significant issue, likely performance impact
```

## Root Cause Analysis

### If Breaches Are High:

1. **Check P-core Count**
   - Verify expected P-cores are online
   - Check CPU topology is correct

2. **Review Thread Priority**
   - Verify critical threads have high priority
   - Check for priority boosting

3. **Examine Hetero Policy**
   - Validate policy settings
   - Check promotion thresholds

4. **Analyze Workload**
   - Too many high-priority threads?
   - Workload exceeds P-core capacity?

## Visualization Recommendations

### Timeline Plot:
```python
# Plot breaches over time
plt.scatter(breach_df['Timestamp'], breach_df['ThreadId'], 
            c=breach_df['Duration_ms'], cmap='Reds')
plt.xlabel('Time (s)')
plt.ylabel('Thread ID')
plt.title('Containment Breaches Over Time')
```

### Core Utilization:
```python
# Show P-core vs E-core usage
pcore_util = calculate_utilization(trace, core_type='P')
ecore_util = calculate_utilization(trace, core_type='E')
plt.plot(pcore_util, label='P-core')
plt.plot(ecore_util, label='E-core')
```

## Related Analyses
- **Hetero Response**: How system promotes threads between core types
- **PPM Validation**: Power performance manager behavior
- **Comprehensive Analysis**: Includes containment as sub-analysis

## Performance Considerations
- Analysis time: ~10-30 seconds for typical trace
- Memory: Requires full trace in memory
- Accuracy: Depends on trace event density
- Filtering: Process filter reduces analysis scope
