# Constraints Validation Logic

## Overview
Evaluates ETL trace data against a set of predefined constraints (rules/thresholds) to validate system behavior and performance requirements.

## Analysis Type
**Constraints-Based Validation Analysis**

## What It Validates
- Power management behavior (PPM constraints)
- Performance thresholds
- Hardware state requirements
- System policy compliance
- Custom user-defined rules

## Input Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trace` | Required | Loaded trace object |
| `constraints_file` | Required | Path to constraints definition file (.txt) |
| `socwatch_file` | Optional | Path to SocWatch summary CSV for additional data |

## Constraints File Format

Constraints are defined using a domain-specific language (DSL):

```python
# Example constraint
CONSTRAINT("Core Frequency Check",
    CONTEXT(PROCESS_NAME("Teams.exe")),
    DEFINE("freq", POWERTRACE_VALUE("Core Frequency")),
    freq > 2000  # MHz threshold
)
```

### Common Constraint Elements:

| Element | Purpose | Example |
|---------|---------|---------|
| `CONSTRAINT()` | Define a validation rule | `CONSTRAINT("name", ...)` |
| `CONTEXT()` | Scope the constraint | `CONTEXT(PROCESS_NAME("app"))` |
| `DEFINE()` | Create variable from trace data | `DEFINE("var", VALUE(...))` |
| `POWERTRACE_VALUE()` | Extract power trace value | `POWERTRACE_VALUE("metric")` |
| `SOCWATCH_VALUE()` | Extract SocWatch value | `SOCWATCH_VALUE("metric")` |
| `TIME_RANGE()` | Time-based filtering | `TIME_RANGE(start, end)` |

## Validation Process

### Step 1: Parse Constraints File
```python
# Load and parse constraint definitions
constraints = parse_constraints_file(constraints_file)
```

### Step 2: Evaluate Each Constraint
For each constraint:
```python
1. Apply CONTEXT filters (process, time range, etc.)
2. Extract required metrics using DEFINE statements
3. Evaluate boolean condition
4. Record result (PASS/FAIL/WARNING)
```

### Step 3: Generate Results DataFrame
```python
results_df = pd.DataFrame({
    'Category': ['PPM', 'Power', 'Performance', ...],
    'Condition': ['Core frequency > 2000', ...],
    'Status': ['PASS', 'FAIL', 'WARNING', ...],
    'AR': ['', 'Action Required message', ...],
    'Details': [additional context...]
})
```

## Constraint Categories

### 1. PPM (Power Performance Manager)
- Core unparking behavior
- Hetero response patterns
- Containment policy compliance
- Performance core utilization

### 2. Power State Validation
- C-state transitions
- Package C-state residency
- Wake-up patterns
- Power floor compliance

### 3. Performance Thresholds
- CPU frequency ranges
- Utilization targets
- Response time requirements
- Throughput minimums

### 4. Hardware Behavior
- Interrupt patterns
- Device state transitions
- Hardware queue depths
- DMA operations

### 5. Custom Application Logic
- Process-specific rules
- Scenario-based validation
- Multi-metric correlations

## Status Values

| Status | Meaning | Action |
|--------|---------|--------|
| **PASS** | Constraint satisfied | No action needed |
| **FAIL** | Constraint violated | Investigation required |
| **WARNING** | Marginal or edge case | Monitor, may need tuning |
| **N/A** | Not applicable | Context not met |
| **ERROR** | Evaluation error | Check constraint definition |

## Output Format

### DataFrame Structure:
```python
{
    'Category': ['PPM', 'Power', 'Performance', ...],
    'Condition': ['Description of check', ...],
    'Status': ['PASS', 'FAIL', 'WARNING', ...],
    'AR': ['Action required text', ...],
    'Value': [actual measured value, ...],      # Optional
    'Threshold': [expected threshold, ...],      # Optional
    'Details': [additional context, ...]         # Optional
}
```

### Example Output:
```python
   Category                    Condition  Status                    AR
0       PPM    PCU Unpark Count > 0      PASS                          
1     Power    Package C-state < 10%     FAIL    Residency too high
2      Perf    Core Freq > 2000 MHz      PASS
3       PPM    Hetero Policy = 1         WARNING Check policy setting
```

## Implementation Location
- **Module**: `ppa.ppa_api.py` (part of SPEED/PPA framework)
- **Class**: `PPAApi`
- **Method**: `analyze_constraints()`
- **Used By**: `teams_KPI_analysis()` in speedlibs_clean.py

## Constraints File Location
- **Default Path**: `speedlibs_service/constraints/teams_constraint.txt`
- **Fallback Path**: `D:\bharath_working_directory\share\LNL\speed_constraints\teams_constraint.txt`

## Example Constraints File

```python
# Teams Meeting Performance Constraints

# Audio FPS Check
CONSTRAINT("Audio FPS",
    DEFINE("audio_fps", CUSTOM_METRIC("audio_frame_rate")),
    audio_fps >= 30
)

# Video Decode Performance
CONSTRAINT("Video Decode FPS",
    CONTEXT(TIME_RANGE(5, 65)),
    DEFINE("decode_fps", CUSTOM_METRIC("decode_frame_rate")),
    decode_fps >= 25
)

# Core Frequency During Meeting
CONSTRAINT("Core Frequency Active",
    CONTEXT(PROCESS_NAME("Teams.exe")),
    DEFINE("freq", POWERTRACE_VALUE("Core Frequency")),
    freq > 2400  # MHz
)

# PPM Hetero Response
CONSTRAINT("Hetero Policy",
    DEFINE("policy", POWERTRACE_VALUE("HeteroPolicy")),
    policy == 1  # Expected policy value
)
```

## Usage Patterns

### Standalone Usage:
```python
from ppa.ppa_api import PPAApi

# Load trace
trace = load_trace(etl_path)

# Analyze constraints
results_df = PPAApi.analyze_constraints(
    trace, 
    constraints_file="path/to/constraints.txt",
    socwatch_file="path/to/socwatch.csv"  # Optional
)

# Check for failures
failures = results_df[results_df['Status'] == 'FAIL']
```

### Via Teams KPI Analysis:
```python
result = teams_kpi_analysis(
    etl_path="path/to/teams.etl",
    operation='constraints',
    constraints_file="path/to/constraints.txt"
)

# Access constraints data
constraints_df = pd.DataFrame(result['constraints_data'])
failures = constraints_df[constraints_df['Status'] == 'FAIL']
```

## Common Constraint Patterns

### 1. Threshold Check
```python
CONSTRAINT("Metric Above Threshold",
    DEFINE("value", SOURCE("metric")),
    value > threshold
)
```

### 2. Range Check
```python
CONSTRAINT("Metric In Range",
    DEFINE("value", SOURCE("metric")),
    (value >= min_val) AND (value <= max_val)
)
```

### 3. State Validation
```python
CONSTRAINT("Correct State",
    DEFINE("state", SOURCE("state_metric")),
    state == expected_state
)
```

### 4. Contextual Check
```python
CONSTRAINT("Process-Specific",
    CONTEXT(PROCESS_NAME("app.exe")),
    DEFINE("metric", SOURCE("value")),
    metric meets_condition
)
```

## Debugging Failed Constraints

### Step 1: Review Constraint Definition
- Check threshold values are reasonable
- Verify metric names are correct
- Ensure context filters are appropriate

### Step 2: Examine Trace Data
- Verify expected events are present
- Check time ranges include relevant activity
- Confirm process/device was active

### Step 3: Analyze AR (Action Required) Message
- Provides specific guidance for failure
- May include recommended settings
- Often includes debugging steps

## Integration with Other Analyses

### Teams KPI Analysis
Constraints validation can check:
- FPS thresholds from FPS analysis
- VCIP alignment rates from VCIP analysis
- Combined multi-metric rules

### Power Analysis
Constraints validate:
- PPM behavior from comprehensive analysis
- Containment policy compliance
- Hetero response patterns

## Performance Considerations

- **Constraint Count**: More constraints = longer evaluation
- **Time Range**: Larger ranges = more data to process
- **Complexity**: Complex conditions take longer to evaluate
- **SocWatch Data**: Adding SocWatch data increases processing time

## Typical Validation Time
- 10-20 constraints: ~5-10 seconds
- 50+ constraints: ~30-60 seconds
- With SocWatch data: Add 10-20 seconds

## Related Analyses
- **Teams KPI Analysis**: Uses constraints to validate FPS/VCIP
- **PPM Validation**: Specialized power management constraints
- **Comprehensive Analysis**: Includes PPM behavior validation
