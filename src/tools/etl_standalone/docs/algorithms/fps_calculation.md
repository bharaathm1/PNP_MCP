# FPS (Frames Per Second) Calculation Logic

## Overview
Calculates video pipeline performance metrics for Microsoft Teams meetings by analyzing various video processing events in ETL traces.

## Analysis Type
**Teams Video Pipeline FPS Analysis**

## What It Measures
- **Decode FPS**: Incoming video stream processing performance
- **Encode FPS**: Outgoing video stream encoding performance  
- **VPBLT FPS**: Video Processor Blit operations (video processing)
- **Camera FPS**: Camera capture performance

## Input Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `etl_path` | Required | Path to ETL trace file |
| `time_range` | `(5, 65)` | Time window for FPS analysis (start_sec, end_sec) |
| `fps_time_range` | `(5, 65)` | Specific FPS analysis window (can differ from main time_range) |

## ETL Events Tracked

### 1. Decoder End Frame Events
- **Event Name**: `ID3D11VideoContext_DecoderEndFrame` with `win:Start`
- **Purpose**: Total video decoding operations
- **Used For**: Calculating decode FPS

### 2. Encode Events
- **Event Name**: `MFCaptureEngine-Sink-Task` with `win:Start`
- **Purpose**: Video encoding operations for outgoing streams
- **Used For**: Calculating encode FPS

### 3. Video Processor Blit Events
- **Event Name**: `ID3D11VideoContext_VideoProcessorBlt` with `win:Start`
- **Purpose**: Video processing/transformation operations
- **Used For**: Calculating VPBLT FPS

### 4. Camera Capture Events
- **Event Name**: `MF_Devproxy_SendBuffersToDevice` with `win:Start`
- **Purpose**: Camera buffer delivery to device
- **Used For**: Calculating camera FPS

## Calculation Formula

### Step-by-Step Process:

1. **Count Events in Time Range**:
   ```
   decoder_end_count = Count of ID3D11VideoContext_DecoderEndFrame events
   encode_count = Count of MFCaptureEngine-Sink-Task events
   vpblt_count = Count of ID3D11VideoContext_VideoProcessorBlt events
   camera_count = Count of MF_Devproxy_SendBuffersToDevice events
   ```

2. **Calculate Derived Counts**:
   ```
   decode_count = decoder_end_count - encode_count
   ```
   (Subtracts encode events from total decoder events to get pure decode operations)

3. **Calculate Duration**:
   ```
   duration = end_time - start_time  (in seconds)
   ```

4. **Calculate FPS Metrics**:
   ```
   decode_fps = decode_count / duration / 9
   encode_fps = encode_count / duration
   vpblt_fps = vpblt_count / duration / 9
   camera_fps = camera_count / duration
   ```

### Why Division by 9?
The `/9` division for decode and VPBLT is for **3x3 grid meetings** (9 video participants).
- Each participant's video is processed separately
- Dividing by 9 gives per-participant FPS
- **Note**: This assumes 9-participant meetings. May not be accurate for other grid sizes.

## Output Metrics

```python
{
    'decode_fps': 14.17,        # FPS for incoming video decoding
    'encode_fps': 15.00,        # FPS for outgoing video encoding
    'vpblt_fps': 12.16,         # FPS for video processing operations
    'camera_fps': 30.00,        # FPS for camera capture
    'decode_events_count': 7653,
    'encode_events_count': 900,
    'vpblt_events_count': 6568,
    'camera_events_count': 1800,
    'duration': 60.0,
    'status': 'SUCCESS'
}
```

## Implementation Location
- **Module**: `speedlibs_service/speedlibs_clean.py`
- **Class**: `TeamsFPS`
- **Method**: `analyze_fps()`
- **Lines**: Approximately 2662-2884

## Original Notebook Reference
- **File**: `TeamsFPS.txt`
- **Key Lines**: 31-40 (main calculation logic)
- **Author Note**: "for queries: pjkoduru"

## Example Usage
```python
# Via Teams KPI Analysis (operation-specific)
result = teams_kpi_analysis(
    etl_path="path/to/teams.etl",
    operation='fps',
    fps_time_range=(5, 65)
)

# Access FPS metrics
decode_fps = result['decode_fps']
encode_fps = result['encode_fps']
```

## Important Notes

1. **Time Range Usage**: 
   - Original notebook does NOT use time_range in `get_events()`
   - Current implementation DOES use time_range for filtering
   - This creates different event counts

2. **Grid Size Assumption**:
   - Hardcoded `/9` assumes 3x3 meeting grid
   - May need adjustment for different meeting sizes

3. **Event Availability**:
   - Not all events may be present in every ETL
   - Missing events result in 0 FPS for that metric

## Typical Values

| Metric | Good Range | Poor Range | Notes |
|--------|-----------|------------|-------|
| Decode FPS | 25-30 | <20 | Per-participant FPS |
| Encode FPS | 28-30 | <25 | Should match camera FPS |
| VPBLT FPS | 25-30 | <20 | Video processing performance |
| Camera FPS | 30 | <28 | Standard webcam rate |

## Related Analyses
- **VCIP Alignment**: Checks if video/audio IPs are synchronized
- **Constraints Validation**: Validates FPS meets threshold requirements
