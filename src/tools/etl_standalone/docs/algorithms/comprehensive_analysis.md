# Comprehensive Analysis Logic

## Overview
A complete, end-to-end analysis that combines multiple analysis types into a single comprehensive report covering Teams performance, power states, PPM behavior, and system performance.

## Analysis Type
**Multi-Domain System Analysis**

## What It Includes

| Analysis Component | Data Extracted | Use Case |
|-------------------|----------------|----------|
| **Combined DataFrame** | All ETW events in structured format | General trace exploration |
| **Hetero Response** | Core type switching behavior | Hybrid architecture validation |
| **Containment Breach** | Thread placement violations | P-core/E-core optimization |
| **Teams KPI** | FPS, VCIP, constraints | Teams meeting quality |
| **Power States** | C-states, wake patterns | Power efficiency |
| **PPM Preprocessing** | Power management events | PPM policy validation |

## Input Parameters

```python
def generate_comprehensive_analysis(
    etl_path: str,
    time_range: tuple = None,
    socwatch_file: str = None,
    constraints_file: str = None,
    include_teams_kpi: bool = True,
    include_power_states: bool = True,
    include_containment: bool = True,
    include_hetero: bool = True,
    include_ppm: bool = True,
    output_format: str = 'dict'  # 'dict' or 'json'
) -> dict:
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `etl_path` | Required | Path to ETL trace file |
| `time_range` | None | Tuple (start_sec, end_sec) or None for full trace |
| `socwatch_file` | None | Optional SocWatch CSV for additional metrics |
| `constraints_file` | None | Optional constraints file for validation |
| `include_teams_kpi` | True | Run Teams FPS/VCIP/constraints |
| `include_power_states` | True | Extract power state data |
| `include_containment` | True | Analyze containment breaches |
| `include_hetero` | True | Extract hetero response data |
| `include_ppm` | True | Preprocess PPM events |
| `output_format` | 'dict' | 'dict' or 'json' serialization |

## Analysis Flow

### Phase 1: Trace Loading
```python
# Load trace once, reuse for all analyses
trace = load_trace_cached(
    etl_file=etl_path,
    time_range=time_range,
    socwatch_summary_file=socwatch_file
)
```

### Phase 2: Extract Base DataFrames
```python
# Combined DataFrame - all events
combined_df = extract_combined_dataframe(trace)

# PPM Preprocessing - power management events
if include_ppm:
    ppm_df = preprocess_ppm_events(trace)
```

### Phase 3: Specialized Analyses (Parallel)
```python
analyses = {}

# Teams KPI (FPS, VCIP, Constraints)
if include_teams_kpi:
    analyses['teams_kpi'] = teams_KPI_analysis(trace, ...)

# Power State Analysis
if include_power_states:
    analyses['power_states'] = analyze_power_states(trace, ...)

# Containment Breach Analysis
if include_containment:
    analyses['containment'] = analyze_containment_breach(trace, ...)

# Hetero Response Analysis
if include_hetero:
    analyses['hetero'] = extract_hetero_response(trace, ...)
```

### Phase 4: Aggregate Results
```python
comprehensive_result = {
    'metadata': { ... },
    'combined_df': combined_df.to_dict('records'),
    'teams_kpi': analyses.get('teams_kpi'),
    'power_states': analyses.get('power_states'),
    'containment': analyses.get('containment'),
    'hetero_response': analyses.get('hetero'),
    'ppm_preprocessing': ppm_df.to_dict('records')
}
```

## Output Structure

### Complete Result Dictionary:
```python
{
    # Metadata
    'metadata': {
        'etl_file': 'path/to/file.etl',
        'file_size_mb': 1234.5,
        'analysis_time_sec': 45.2,
        'time_range': (0, 60),
        'socwatch_file': 'path/to/socwatch.csv',
        'timestamp': '2024-01-15T10:30:00'
    },
    
    # Combined DataFrame - All Events
    'combined_df': [
        {
            'TimeStamp': 0.123,
            'Event': 'ProcessCreate',
            'ProcessName': 'Teams.exe',
            'ThreadId': 1234,
            'Details': { ... }
        },
        ...
    ],
    
    # Teams KPI Analysis
    'teams_kpi': {
        'fps_data': [...],
        'vcip_data': [...],
        'constraints_data': [...]
    },
    
    # Power State Analysis
    'power_states': {
        'cstate_residency': [...],
        'wake_events': [...],
        'package_cstates': [...]
    },
    
    # Containment Breach Analysis
    'containment': {
        'breach_events': [...],
        'summary': {
            'total_breaches': 12,
            'compliance_rate': 96.5,
            ...
        }
    },
    
    # Hetero Response Analysis
    'hetero_response': [
        {
            'Timestamp': 1.234,
            'ThreadId': 5678,
            'OldCore': 'E',
            'NewCore': 'P',
            'Delay_ms': 15.2
        },
        ...
    ],
    
    # PPM Preprocessing
    'ppm_preprocessing': [
        {
            'Timestamp': 2.345,
            'Event': 'UnparkCore',
            'CoreNumber': 0,
            'Reason': 'HighUtilization'
        },
        ...
    ]
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Function**: `generate_comprehensive_analysis()`
- **Lines**: Approximately 3100-3400
- **Dependencies**: All major analysis functions

## Component Details

### 1. Combined DataFrame
**Purpose**: Unified view of all ETW events  
**Content**: Process, thread, file, registry, network events  
**Size**: Large (10k-100k+ rows for typical trace)  
**Use**: General exploration, custom queries

**Sample Columns**:
- TimeStamp
- Event (ProcessCreate, ThreadStart, FileIO, etc.)
- ProcessName
- ThreadId
- CPU
- Details (event-specific data)

### 2. PPM Preprocessing
**Purpose**: Extract power performance manager events  
**Content**: Core parking, unparking, frequency changes  
**Size**: Medium (1k-10k rows)  
**Use**: PPM policy validation

**Key Events**:
- PCU_UNPARK_CORE
- PCU_PARK_CORE
- HETERO_RESPONSE_PROMOTION
- HETERO_RESPONSE_DEMOTION
- PERF_STATE_CHANGE

### 3. Hetero Response
**Purpose**: Track thread migration between core types  
**Content**: Thread ID, old core, new core, delay  
**Size**: Small to medium (100-5k events)  
**Use**: Hybrid architecture optimization

**Metrics**:
- Promotion delay (E→P)
- Demotion delay (P→E)
- Thread affinity changes
- Core type efficiency

### 4. Containment Breach
**Purpose**: Identify thread placement violations  
**Content**: Breach events, durations, impact  
**Size**: Small (0-100 events typically)  
**Use**: Thread scheduling validation

**See**: [containment_breach.md](containment_breach.md) for details

### 5. Teams KPI
**Purpose**: Teams meeting quality metrics  
**Content**: FPS, VCIP alignment, constraints  
**Size**: Variable (depends on meeting duration)  
**Use**: Teams performance validation

**See**: 
- [fps_calculation.md](fps_calculation.md)
- [vcip_alignment.md](vcip_alignment.md)
- [constraints_validation.md](constraints_validation.md)

### 6. Power States
**Purpose**: System power management analysis  
**Content**: C-state residency, wake sources  
**Size**: Medium (1k-10k events)  
**Use**: Power efficiency optimization

**Key Data**:
- C-state entry/exit events
- Residency percentages
- Wake-up sources
- Package C-states

## Usage Patterns

### Full Comprehensive Analysis:
```python
# Run everything
result = generate_comprehensive_analysis(
    etl_path="path/to/teams_meeting.etl",
    time_range=(10, 70),  # Meeting period
    socwatch_file="path/to/socwatch.csv",
    constraints_file="path/to/constraints.txt"
)

# Access any component
fps_data = result['teams_kpi']['fps_data']
breaches = result['containment']['breach_events']
ppm_events = result['ppm_preprocessing']
```

### Selective Analysis:
```python
# Only Teams KPI + Power States
result = generate_comprehensive_analysis(
    etl_path="path/to/trace.etl",
    include_teams_kpi=True,
    include_power_states=True,
    include_containment=False,  # Skip
    include_hetero=False,        # Skip
    include_ppm=False            # Skip
)
```

### JSON Export:
```python
# Get JSON-serializable result
result = generate_comprehensive_analysis(
    etl_path="path/to/trace.etl",
    output_format='json'
)

# Save to file
with open('analysis_result.json', 'w') as f:
    json.dump(result, f, indent=2)
```

## Performance Characteristics

### Typical Analysis Times:

| Trace Size | Full Analysis | Teams KPI Only | Power States Only |
|------------|---------------|----------------|-------------------|
| 500MB      | ~30-45s       | ~15-20s        | ~10-15s          |
| 1GB        | ~60-90s       | ~30-40s        | ~20-30s          |
| 2GB+       | ~120-180s     | ~60-80s        | ~40-60s          |

### Memory Usage:
- Trace in memory: ~0.5-1x file size
- Combined DataFrame: ~100-500MB
- All results combined: ~200-800MB
- Recommend 8GB+ RAM for large traces

## Output Size Considerations

### Combined DataFrame:
- Can be very large (100k+ rows)
- Consider filtering by time range
- Use `output_format='json'` for file storage

### JSON Serialization:
- Converts pandas DataFrames to lists of dicts
- Handles datetime, numpy types
- Safe for REST API responses

## REST API Integration

### Endpoint:
```
POST /comprehensive_analysis
```

### Request:
```json
{
    "etl_path": "path/to/trace.etl",
    "time_range": [10, 70],
    "include_teams_kpi": true,
    "include_power_states": true,
    "include_containment": true,
    "include_hetero": true,
    "include_ppm": true
}
```

### Response:
```json
{
    "status": "success",
    "data": {
        "metadata": { ... },
        "combined_df": [ ... ],
        "teams_kpi": { ... },
        ...
    }
}
```

## Use Cases

### 1. Teams Meeting Analysis
```python
result = generate_comprehensive_analysis(
    etl_path="teams_meeting.etl",
    time_range=(5, 65),  # 1 minute meeting
    include_teams_kpi=True,
    include_power_states=True,
    include_ppm=True
)

# Check meeting quality
fps = result['teams_kpi']['fps_data'][0]['decode_fps']
vcip = result['teams_kpi']['vcip_data'][0]['alignment_status']
print(f"FPS: {fps:.1f}, VCIP: {vcip}")
```

### 2. Power Efficiency Study
```python
result = generate_comprehensive_analysis(
    etl_path="idle_system.etl",
    include_teams_kpi=False,
    include_power_states=True,
    include_ppm=True
)

# Analyze power states
power_data = result['power_states']
c6_residency = calculate_residency(power_data, 'C6')
print(f"C6 Residency: {c6_residency:.1f}%")
```

### 3. Hybrid Architecture Validation
```python
result = generate_comprehensive_analysis(
    etl_path="workload.etl",
    include_containment=True,
    include_hetero=True,
    include_ppm=True
)

# Check thread placement
breaches = result['containment']['summary']['total_breaches']
hetero_delay = result['hetero_response']['avg_delay_ms']
print(f"Breaches: {breaches}, Hetero Delay: {hetero_delay:.1f}ms")
```

## Related Analyses
- All individual analysis components
- Can be used as foundation for custom reports
- Provides data for machine learning models
