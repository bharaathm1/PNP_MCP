# Teams Workload Constraints Reference

## Overview
Validation constraints specific to Microsoft Teams video playback (VPB) workload. Ensures proper system configuration for Teams video playback power optimization.

## Purpose
Automated validation that system hardware, drivers, and OS features are correctly configured for Teams video playback power measurements.

## Constraint Categories

### 1. PPM Package (Power Performance Management)

#### PPM Package Installation
- **Category**: OS
- **Condition**: Checks for LowPower Profile (ProfileId = 4)
- **Event**: `Microsoft-Windows-Kernel-Processor-Power/ProfileChange`
- **Action Required**: PPM package not properly installed. LowPower profile for VPB not detected
- **Note**: Currently commented out in constraint file

### 2. Hybrid CPU Architecture

#### Hybrid CPU Detection
- **Category**: OS
- **Message**: Checking for whether OS is detecting Hybrid CPU architecture
- **Condition**: 
  ```
  GENERIC_EVENT("Microsoft-Windows-Kernel-Processor-Power/HeterogeneousPoliciesRundown")
  - HeterogeneousSystemType == 5
  - DefaultPolicy == 5
  ```
- **Action Required**: OS didn't detect Hybrid CPU. Please check whether Atoms are disabled or file HSD
- **Interpretation**: System must be recognized as hybrid (P-cores + E-cores) for proper scheduling

### 3. Media Resolution

#### Video Resolution Check
- **Category**: OS
- **Message**: Checking for Media Resolution
- **Condition**:
  ```
  GENERIC_EVENT("Microsoft-Windows-DxgKrnl/MMIOFlipMultiPlaneOverlay")
  - LayerIndex == 1
  - SrcRect.right == 1920
  - SrcRect.bottom == 1080
  ```
- **Action Required**: VPB Clip is not 1080p, please check clip resolution or MPO is disabled
- **Interpretation**: Teams power testing requires 1080p video for consistent measurements

#### Video Batching
- **Category**: OS
- **Message**: Checking for Video Batching
- **Condition**: `GENERIC_EVENT("Microsoft-Windows-MediaEngine/Batch")`
- **Action Required**: Make sure the KPI was run in full screen
- **Interpretation**: Video batching improves power efficiency; requires fullscreen mode

### 4. DPST (Display Power Saving Technology)

#### DPST Driver Events
- **Category**: Driver
- **Message**: Checking for DPST
- **Condition**:
  ```
  GENERIC_EVENT("Intel-Gfx-Driver-Display/DisplayPcDPST/Program")
  OR
  GENERIC_EVENT("Intel-Gfx-Driver-Display/DisplayPcXPST/Program")
  - TimeStamp between 20s-71s
  - Interval between 0-100ms
  ```
- **Action Required**: Make sure DPST is enabled by checking the Intel Graphics Control Panel or FeatureTestControl regkey (Bit 04 should be set for DPST to work)
- **Interpretation**: DPST dynamically adjusts display brightness to save power

#### DPST DPC Timer
- **Category**: OS
- **Message**: Checking for DPST
- **Condition**:
  ```
  GENERIC_EVENT("DPCTmr")
  - Image/Function contains "igdkmdn64.sys"
  - TimeStamp between 20s-71s
  - Interval between 0-100ms
  ```
- **Action Required**: Make sure DPST is enabled
- **Interpretation**: Verifies DPST driver is actively running

### 5. Video Decode

#### Video Decode Detection
- **Category**: OS
- **Message**: Checking for Video Decode
- **Condition**:
  ```
  GENERIC_EVENT("Microsoft-Windows-MediaEngine/ProcessFrame")
  OR
  GENERIC_EVENT("Microsoft-Windows-MediaEngine/PresentFrame")
  ```
- **Action Required**: No Video Decode was detected. Make sure the KPI was run correctly
- **Interpretation**: Ensures video is actually playing during trace

#### Video Glitch Detection
- **Category**: OS
- **Message**: Checking for Video Glitch
- **Condition**: `GENERIC_EVENT("Microsoft-Windows-MediaEngine/VideoFrameGlitch")` during 20-71s
- **Action Required**: Video Glitch detected, this is not expected. Please quiesce the system and try again. If issue still persists file a Bug
- **Interpretation**: Frame drops indicate system instability or performance issues

### 6. Video Processing

#### VpBlt CSC (Color Space Conversion)
- **Category**: OS
- **Message**: Checking NV12 to YUY2 CSC
- **Condition**:
  ```
  GENERIC_EVENT("Microsoft-Windows-MediaFoundation-MSVProc/D3DVideoProcessorBlt")
  - SourceFormat == 103 (NV12)
  - DestFormat == 107 (YUY2)
  ```
- **Action Required**: Make sure NV12 MPO is enabled by checking the DisplayFeatureControl registry key. Bit 01 should be set to enable NV12 MPO
- **Interpretation**: Proper color space conversion reduces power consumption

### 7. MPO (Multi-Plane Overlay)

#### MPO Plane Enabled
- **Category**: OS
- **Message**: Checking for MPO (VPB) Plane
- **Condition**:
  ```
  GENERIC_EVENT("Microsoft-Windows-DxgKrnl/DisplayConfigPlaneChange")
  - PlaneIndex == 1
  - SrcRect: 1920x1080
  - Enabled == true (before 45.5s)
  - Enabled == false (after 45.5s)
  ```
- **Action Required**: MPO (Overlay 1) is not enabled or MPO is disabled/not working
- **Interpretation**: MPO allows video to bypass composition, saving power

### 8. Audio Offload

#### Audio Offload Detection
- **Category**: OS
- **Message**: Checking for Audio Offload
- **Condition**:
  ```
  GENERIC_EVENT("Microsoft-Windows-MediaFoundation-Performance-Core/
                AudEngineStream_FillRenderBuffer_Task")
  - TimeStamp between 12s-74s
  - Total interval > 700ms
  ```
- **Action Required**: If this feature is disabled it leads to a wakeup every 10ms to render Audio. To verify if the feature is enabled make sure "Allow hardware acceleration of audio with this device" box is checked in the Speaker Properties. If it's enabled and the issue is still observed file a Bug
- **Interpretation**: Audio offload reduces CPU wakeups from every 10ms to much longer intervals

#### Audio Offload (FULL Check)
- **Category**: OS
- **Message**: Checking for Audio Offload (FULL)
- **Condition**: Same as above but with stricter validation (< 700ms indicates failure)
- **Action Required**: Same as above
- **Interpretation**: More stringent version that fails if audio offload interval is too short

## Event Provider Reference

### Kernel Processor Power
- **Provider**: `Microsoft-Windows-Kernel-Processor-Power`
- **Events Used**:
  - `ProfileChange` - Power profile transitions
  - `HeterogeneousPoliciesRundown` - Hybrid CPU detection

### DxgKrnl (DirectX Kernel)
- **Provider**: `Microsoft-Windows-DxgKrnl`
- **Events Used**:
  - `MMIOFlipMultiPlaneOverlay` - MPO video overlay
  - `DisplayConfigPlaneChange` - Display plane enable/disable

### Media Engine
- **Provider**: `Microsoft-Windows-MediaEngine`
- **Events Used**:
  - `Batch` - Video batching
  - `ProcessFrame` - Video frame processing
  - `PresentFrame` - Video frame presentation
  - `VideoFrameGlitch` - Frame drops/glitches

### Media Foundation
- **Provider**: `Microsoft-Windows-MediaFoundation-MSVProc`
- **Events Used**:
  - `D3DVideoProcessorBlt` - Video color space conversion

### Audio Engine
- **Provider**: `Microsoft-Windows-MediaFoundation-Performance-Core`
- **Events Used**:
  - `AudEngineStream_FillRenderBuffer_Task` - Audio rendering

### Intel Graphics Driver
- **Provider**: `Intel-Gfx-Driver-Display`
- **Events Used**:
  - `DisplayPcDPST/Program` - DPST brightness adjustments
  - `DisplayPcXPST/Program` - Extended DPST

## Validation Workflow

```
Teams Video Playback Test
    ↓
Capture ETL Trace
    ↓
Evaluate Teams Constraints
    ↓
Check System Configuration
    ├─ Hybrid CPU detected?
    ├─ 1080p video playing?
    ├─ MPO enabled?
    ├─ DPST active?
    ├─ Audio offload working?
    ├─ Video batching enabled?
    └─ No glitches detected?
    ↓
Generate Pass/Fail Report
    ↓
If FAIL → Apply recommended actions
```

## Common Failure Scenarios

### Configuration Issues
| Constraint Failure | Likely Cause | Resolution |
|-------------------|--------------|------------|
| Hybrid CPU not detected | BIOS disabled E-cores | Enable all cores in BIOS |
| MPO not enabled | Registry setting | Check DisplayFeatureControl regkey Bit 01 |
| DPST not active | Graphics setting | Enable in Intel Graphics Control Panel, FeatureTestControl Bit 04 |
| Audio offload disabled | Audio property | Enable "Allow hardware acceleration" in Speaker Properties |
| Wrong resolution | Test configuration | Use 1080p video clip |
| No fullscreen | Test execution | Run video in fullscreen mode |

### Runtime Issues
| Constraint Failure | Likely Cause | Resolution |
|-------------------|--------------|------------|
| Video glitch detected | System unstable | Quiesce system, close background apps |
| No video decode | Test not running | Verify video is actually playing |
| No video batching | Window mode | Switch to fullscreen |

## Registry Keys

### Display Feature Control
**Location**: Check graphics driver settings
- **Bit 01**: NV12 MPO enable
- **Bit 04**: DPST enable

### Audio Properties
**Location**: Control Panel → Sound → Speaker Properties → Advanced
- **Setting**: "Allow hardware acceleration of audio with this device"

## Time Regions

Most constraints use specific time windows:
- **20-71 seconds**: Core measurement window for DPST, glitches
- **12-74 seconds**: Audio offload measurement window
- **< 45.5 seconds**: MPO plane should be enabled
- **> 45.5 seconds**: MPO plane should be disabled

These timing windows correspond to the Teams video playback test phases.

## Related Constraints
- [PPM Constraints](constraints_ppm.md) - Power management constraints
- [PPM Settings Constraints](constraints_ppm_val.md) - PPM parameter validation
- [Constraints Validation](constraints_validation.md) - General constraint framework

## Related Analyses
- FPS Calculation - Video decode framerate
- VCIP Alignment - IP alignment for power efficiency
- Comprehensive Analysis - Full Teams workload analysis

## Implementation Location
- **Constraint File**: `speedlibs_service/constraints/teams_constraint.txt`
- **Validation Module**: Part of Teams KPI analysis comprehensive validation
- **Related Code**: `speedlibs_service/speedlibs_clean.py` - EtlTrace class

## Debugging Commands

### Check Hybrid CPU
```python
# Look for HeterogeneousPoliciesRundown event
hetero_events = trace.get_generic_events("Microsoft-Windows-Kernel-Processor-Power/HeterogeneousPoliciesRundown")
```

### Check MPO Status
```python
# Look for DisplayConfigPlaneChange events
mpo_events = trace.get_generic_events("Microsoft-Windows-DxgKrnl/DisplayConfigPlaneChange")
# Filter for PlaneIndex == 1
```

### Check Audio Offload
```python
# Look for audio buffer fill events
audio_events = trace.get_generic_events("Microsoft-Windows-MediaFoundation-Performance-Core/AudEngineStream_FillRenderBuffer_Task")
# Calculate intervals between events
```

## Best Practices

1. **Pre-Test Validation**: Run constraint checks before power measurement
2. **System Quiescence**: Ensure no background activity before test
3. **Configuration Verification**: Validate all registry keys and settings
4. **Trace Review**: Check for video glitches and unexpected events
5. **Consistent Environment**: Use same video clip, resolution, and window mode

## Status Indicators

- ✅ **PASS**: All features working as expected, valid for power measurement
- ❌ **FAIL**: Configuration issue, fix before measuring power
- ⚠️ **WARNING**: Feature detected but may not be optimal
