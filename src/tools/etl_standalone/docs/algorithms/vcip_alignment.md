# VCIP (4-IP Alignment) Analysis Logic

## Overview
Analyzes audio-centric IP block alignment for Microsoft Teams meetings. Checks how well slower IP blocks (Media, IPU, WLAN) synchronize with the fastest Audio IP block.

## Analysis Type
**4-IP Audio-Centric Alignment Analysis**

## What It Measures
- **Media → Audio Alignment**: How well Media IP aligns with Audio IP
- **IPU → Audio Alignment**: How well IPU (camera) IP aligns with Audio IP
- **WLAN → Audio Alignment**: How well WLAN hardware interrupts align with Audio hardware interrupts

## Why Audio-Centric?
Audio IP is typically the **fastest/most frequent**, so other IPs should synchronize TO audio for best Teams performance.

## Input Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `etl_path` | Required | Path to ETL trace file |
| `time_range` | `(2, 10)` | Time window for VCIP analysis (start_sec, end_sec) |
| `vcip_time_range` | `(2, 10)` | Specific VCIP analysis window |

## Alignment Thresholds

| Event Type | Threshold | Description |
|------------|-----------|-------------|
| Regular Events | 2.0 ms | For Media, IPU events vs Audio events |
| HW Interrupts | 2.5 ms | For WLAN HW vs Audio HW interrupts |

## ETL Events Tracked

### 1. Audio Events (Reference/Target)
- **Event Name**: `AudioCore_Pump_GetCurrentPadding_Task` with `win:Stop`
- **Purpose**: Audio processing pipeline events
- **Role**: Target for other IPs to align to
- **Timestamp Unit**: Milliseconds (converted from nanoseconds / 1000)

### 2. Media Events
- **Event Name**: `Decode_DDI_IP_Alignment` with `win:Stop`
- **Purpose**: Media decoding IP alignment markers
- **Role**: Source events that should align to Audio
- **Timestamp Unit**: Milliseconds

### 3. IPU Events (Camera)
- **Event Name**: `Intel-Camera-Intel(R) AVStream Camera` with `IP_ALIGNMENT`
- **Purpose**: Camera/IPU IP alignment markers
- **Role**: Source events that should align to Audio
- **Timestamp Unit**: Milliseconds

### 4. WLAN Hardware Interrupts
- **Source**: `get_interrupts()` DataFrame
- **Filter**: Name contains `netwaw16.sys` AND Type contains `HW`
- **Purpose**: WLAN hardware interrupt timing
- **Role**: Source interrupts that should align to Audio HW
- **Timestamp**: End(s) column * 1000 (converted to ms)

### 5. Audio Hardware Interrupts
- **Source**: `get_interrupts()` DataFrame
- **Filter**: Name contains `intcaudiobus.sys` AND Type contains `HW`
- **Purpose**: Audio hardware interrupt timing
- **Role**: Target for WLAN HW interrupts to align to
- **Timestamp**: End(s) column * 1000 (converted to ms)

## Calculation Algorithm

### Original Notebook Logic (Sequential):
```python
# Events are processed in order as they appear
for event in etl_events:
    if event is Audio:
        audio_ts = event.timestamp
        # Check if PREVIOUSLY seen IPU/Media align with THIS audio
        if abs(ipu_ts - audio_ts) <= threshold:
            aligned_count += 1
```
**Characteristic**: Order-dependent, only checks most recent timestamp

### Current Implementation Logic (All-Pairs):
```python
# After collecting all events, find best matches
for source_event in source_events:
    closest_target = None
    closest_delta = infinity
    
    for target_event in target_events:
        delta = abs(source_event.ts - target_event.ts)
        if delta <= threshold and delta < closest_delta:
            closest_delta = delta
            closest_target = target_event
    
    if closest_target:
        aligned_count += 1
```
**Characteristic**: Order-independent, finds globally closest match

## Step-by-Step Calculation

### Step 1: Extract Events
```
1. Extract all Audio events in time range
2. Extract all Media events in time range  
3. Extract all IPU events in time range
4. Extract WLAN HW interrupts (filter by driver name)
5. Extract Audio HW interrupts (filter by driver name)
```

### Step 2: Calculate Alignments

For each alignment type (Media→Audio, IPU→Audio, WLAN→Audio):

```python
aligned_count = 0
total_source_events = len(source_events)

for each source_event:
    # Find closest target event within threshold
    min_delta = infinity
    found_match = False
    
    for each target_event:
        delta = abs(source_event.timestamp - target_event.timestamp)
        
        if delta <= threshold:
            if delta < min_delta:
                min_delta = delta
                found_match = True
    
    if found_match:
        aligned_count += 1

alignment_rate = (aligned_count / total_source_events) * 100
```

### Step 3: Generate Results
```python
media_to_audio_rate = (media_aligned / media_total) * 100
ipu_to_audio_rate = (ipu_aligned / ipu_total) * 100  
wlan_to_audio_rate = (wlan_aligned / wlan_total) * 100
```

## Output Metrics

```python
{
    'media_to_audio_alignment': 95.5,  # or 'NOT_FOUND' if no events
    'ipu_to_audio_alignment': 92.3,
    'wlan_to_audio_alignment': 88.7,
    
    'audio_events_count': 240,
    'media_events_count': 220,
    'ipu_events_count': 215,
    'wlan_hw_events_count': 236,
    'audio_hw_events_count': 240,
    
    'missing_events': ['IPU'],  # List of missing event types
    'overall_status': 'PASS',  # PASS/MARGINAL/FAIL/NO_DATA
    'assessment': 'All IPs achieve excellent alignment (>=80%)'
}
```

## Status Determination

| Condition | Status | Description |
|-----------|--------|-------------|
| All 3 IPs >= 80% | PASS | Excellent alignment |
| 2/3 IPs >= 80% | MARGINAL | Acceptable but room for improvement |
| < 2/3 IPs >= 80% | FAIL | Poor alignment, performance issues likely |
| No events found | NO_DATA | Cannot perform analysis |

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `VCIP_SingleETL_Enhanced`
- **Method**: `analyze_4ip_alignment()`
- **Lines**: Approximately 2251-2660

## Original Notebook Reference
- **File**: `VCIP_ETL.txt`
- **Key Lines**: 
  - 24-68: Main event loop and alignment logic
  - 75-115: WLAN hardware interrupt alignment
- **Author Note**: "for queries: pjkoduru"

## Key Differences: Notebook vs Implementation

| Aspect | Original Notebook | Current Implementation |
|--------|------------------|----------------------|
| Time Range | NOT used in get_events() | USED in get_events() |
| Matching Logic | Sequential (order-dependent) | All-pairs (finds best match) |
| Tolerance | Single 2.5ms for all | 2.0ms events, 2.5ms HW |
| Missing Events | Crashes/errors | Graceful handling with "NOT_FOUND" |

## Example Usage
```python
# Via Teams KPI Analysis (operation-specific)
result = teams_kpi_analysis(
    etl_path="path/to/teams.etl",
    operation='vcip',
    vcip_time_range=(2, 10)
)

# Access alignment rates
media_align = result['media_to_audio_alignment']
ipu_align = result['ipu_to_audio_alignment']
wlan_align = result['wlan_to_audio_alignment']
```

## Common Issues

### "NOT_FOUND" Results
**Cause**: Required events not present in ETL
**Solutions**:
- Verify ETL was captured with correct providers
- Check time range includes activity period
- Confirm camera/WLAN were active during capture

### Low Alignment Rates (<60%)
**Possible Causes**:
- Power management issues (IP blocks in different power states)
- Driver/firmware problems
- Hardware synchronization issues
- Thermal throttling

## Typical Values

| Metric | Good Range | Acceptable | Poor |
|--------|-----------|------------|------|
| Media → Audio | 95-100% | 80-95% | <80% |
| IPU → Audio | 90-100% | 75-90% | <75% |
| WLAN → Audio | 85-95% | 70-85% | <70% |

## Related Analyses
- **FPS Calculation**: Video performance metrics
- **Constraints Validation**: Checks alignment against thresholds
- **Power State Analysis**: Can affect IP alignment
