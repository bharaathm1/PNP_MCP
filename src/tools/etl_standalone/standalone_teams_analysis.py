"""
Standalone Teams KPI Analysis Script
======================================

Designed to run via: speed.exe run standalone_teams_analysis.py <args>

This script provides the SAME functionality and output format as the 
speedlibs_service teams_KPI_analysis endpoint, but runs in an 
independent SPEED kernel instance.

Usage:
    speed.exe run standalone_teams_analysis.py --etl_file <path> --output_dir <path> [options]

Output:
    - teams_kpi_results.pkl (same format as speedlibs_service)
    - teams_kpi_results.json (JSON format for easy reading)
    - constraints_data.csv (flattened constraints DataFrame)

Author: Generated for speedlibs_service fallback architecture
Date: January 16, 2026
"""

import sys
import os
import json
import argparse
from datetime import datetime
import pickle
from pathlib import Path

# Add SpeedLibs project directory to Python path
speedlibs_project_path = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if speedlibs_project_path not in sys.path:
    sys.path.insert(0, speedlibs_project_path)

import pandas as pd
import numpy as np

# Apply NumPy compatibility patch
if not hasattr(np, 'int'):
    np.int = int
    np.float = float
    np.complex = complex
    np.bool = bool

# Import SPEED kernel modules
try:
    from ppa.ppa_api import PPAApi
    import tracedm  # Need full tracedm for load_trace()
    SPEED_AVAILABLE = True
    print("[OK] SPEED kernel PPA API imported successfully")
except ImportError as e:
    print(f"[ERROR] SPEED kernel modules not available: {e}")
    SPEED_AVAILABLE = False
    sys.exit(1)

# Default constraints file for Teams (relative to ETL_ANALYZER folder)
_CURRENT_DIR = Path(__file__).parent.parent  # ETL_ANALYZER folder
DEFAULT_TEAMS_CONSTRAINT_FILE = str(_CURRENT_DIR / "constraints" / "teams_constraint.txt")


def run_teams_kpi_analysis(etl_file_path, output_dir,
                           time_range=(0, 60),
                           vcip_time_range=(2, 10),
                           fps_time_range=(5, 65),
                           constraints_file=None):
    """
    Run Teams KPI analysis - SAME logic as speedlibs_service endpoint
    
    Args:
        etl_file_path: Path to ETL file
        output_dir: Output directory for results
        time_range: Main trace time range (start, end)
        vcip_time_range: VCIP analysis time range
        fps_time_range: FPS analysis time range
        constraints_file: Path to Teams constraints file
    
    Returns:
        dict: Flattened Teams KPI results (same format as API)
    """
    print("=" * 80)
    print("[STANDALONE] TEAMS KPI ANALYSIS")
    print("=" * 80)
    
    if not SPEED_AVAILABLE:
        print("[ERROR] SPEED kernel not available")
        return {}
    
    # Set default constraints file (only if it exists)
    if constraints_file is None:
        if os.path.exists(DEFAULT_TEAMS_CONSTRAINT_FILE):
            constraints_file = DEFAULT_TEAMS_CONSTRAINT_FILE
            print(f"[CONFIG] Using default constraints: {constraints_file}")
        else:
            constraints_file = None
            print(f"[CONFIG] Default constraints file not found, will skip constraints analysis")
    
    # Determine output directory (same as ETL file directory if not specified)
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(etl_file_path))
        print(f"[FILE] Using ETL file directory for output: {output_dir}")
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    # Generate base filename with timestamp (matching comprehensive analysis format)
    etl_basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{etl_basename}_{timestamp_str}"
    
    print(f"[FILE] Output base filename: {base_filename}")
    
    try:
        print(f"[FILE] ETL: {etl_file_path}")
        print(f"[TIME] Ranges: Main{time_range}, VCIP{vcip_time_range}, FPS{fps_time_range}")
        
        # 1. Load trace once using tracedm.load_trace() to get MultiTrace object
        # This returns MultiTrace (not EtlTrace) which is compatible with all analysis methods
        print(f"[TRACE] Loading trace with time_range={time_range}...")
        trace = tracedm.load_trace(etl_file=etl_file_path)
        print(f"[TRACE] [OK] MultiTrace loaded successfully (type: {type(trace).__name__})")
        
        # 2. VCIP Analysis
        print(f"[VCIP] Running VCIP alignment analysis...")
        vcip_results = analyze_vcip_alignment(trace, vcip_time_range)
        
        # 3. FPS Analysis
        print(f"[FPS] Running Teams FPS analysis...")
        fps_results = analyze_teams_fps(trace, fps_time_range)
        
        # 4. Constraints Analysis
        print(f"[CONSTRAINTS] Running constraints analysis...")
        constraints_df = pd.DataFrame()  # Initialize as empty
        
        # Check if constraints file exists
        if constraints_file and os.path.exists(constraints_file):
            try:
                constraints_df = PPAApi.analyze_constraints(trace, constraints_file)
                print(f"[CONSTRAINTS] [OK] Constraints analysis complete: {len(constraints_df)} results")
            except Exception as e:
                print(f"[CONSTRAINTS] [WARNING] Constraints analysis failed: {e}")
                print(f"[CONSTRAINTS] Continuing without constraints data...")
        else:
            print(f"[CONSTRAINTS] [WARNING] Constraints file not found: {constraints_file}")
            print(f"[CONSTRAINTS] Skipping constraints analysis...")
        
        # 5. Create flat, API-friendly dictionary (SAME format as speedlibs_service)
        api_result = {
            # Raw alignment rates
            "media_to_audio_alignment": vcip_results.get('media_to_audio', 'ERROR'),
            "ipu_to_audio_alignment": vcip_results.get('ipu_to_audio', 'ERROR'),
            "wlan_to_audio_alignment": vcip_results.get('wlan_to_audio', 'ERROR'),
            
            # Raw FPS values
            "decode_fps": fps_results.get('decode_fps', 0.0),
            "encode_fps": fps_results.get('encode_fps', 0.0),
            "vpblt_fps": fps_results.get('vpblt_fps', 0.0),
            "camera_fps": fps_results.get('camera_fps', 0.0),
            
            # Event counts (for context)
            "audio_events_count": vcip_results.get('audio_events_count', 0),
            "media_events_count": vcip_results.get('media_events_count', 0),
            "ipu_events_count": vcip_results.get('ipu_events_count', 0),
            "wlan_hw_events_count": vcip_results.get('wlan_hw_events_count', 0),
            "audio_hw_events_count": vcip_results.get('audio_hw_events_count', 0),
            
            # Video event counts
            "decode_events_count": fps_results.get('decode_events_count', 0),
            "encode_events_count": fps_results.get('encode_events_count', 0),
            "vpblt_events_count": fps_results.get('vpblt_events_count', 0),
            "camera_events_count": fps_results.get('camera_events_count', 0),
            
            # Constraints data (SAME format as API)
            "constraints_count": len(constraints_df) if not constraints_df.empty else 0,
            "constraints_columns": list(constraints_df.columns.tolist()) if not constraints_df.empty else [],
            "constraints_data": constraints_df.to_dict('records') if not constraints_df.empty else [],
            
            # Analysis metadata
            "etl_file": etl_file_path,
            "main_time_start": time_range[0],
            "main_time_end": time_range[1],
            "vcip_time_start": vcip_time_range[0],
            "vcip_time_end": vcip_time_range[1],
            "fps_time_start": fps_time_range[0],
            "fps_time_end": fps_time_range[1],
            "constraints_file": constraints_file,
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            
            # Missing events list
            "missing_events": vcip_results.get('missing_events', []),
            
            # Success flags
            "vcip_analysis_completed": 'error' not in vcip_results,
            "fps_analysis_completed": 'error' not in fps_results,
            "constraints_analysis_completed": constraints_df is not None and not constraints_df.empty
        }
        
        # 6. Save to pickle with timestamped filename
        pickle_file = os.path.join(output_dir, f'{base_filename}_teams_kpi.pkl')
        print(f"[FILE] Saving results to pickle: {pickle_file}")
        with open(pickle_file, 'wb') as f:
            pickle.dump(api_result, f)
        print(f"[OK] Pickle file saved: {pickle_file}")
        
        # 7. Save to JSON for easy reading with timestamped filename
        json_file = os.path.join(output_dir, f'{base_filename}_teams_kpi.json')
        print(f"[FILE] Saving results to JSON: {json_file}")
        with open(json_file, 'w') as f:
            json.dump(api_result, f, indent=2, default=str)
        print(f"[OK] JSON file saved: {json_file}")
        
        # 8. Save constraints DataFrame as CSV with timestamped filename
        if not constraints_df.empty:
            csv_file = os.path.join(output_dir, f'{base_filename}_constraints.csv')
            constraints_df.to_csv(csv_file, index=False)
            print(f"[OK] Constraints CSV saved: {csv_file}")
        
        # 9. Save metadata with timestamped filename
        metadata = {
            "analysis_type": "teams_kpi_analysis",
            "etl_file": etl_file_path,
            "etl_basename": etl_basename,
            "output_dir": output_dir,
            "base_filename": base_filename,
            "timestamp": datetime.now().isoformat(),
            "execution_mode": "standalone_speed_exe",
            "time_ranges": {
                "main": time_range,
                "vcip": vcip_time_range,
                "fps": fps_time_range
            },
            "results_summary": {
                "media_to_audio": api_result['media_to_audio_alignment'],
                "ipu_to_audio": api_result['ipu_to_audio_alignment'],
                "wlan_to_audio": api_result['wlan_to_audio_alignment'],
                "decode_fps": api_result['decode_fps'],
                "encode_fps": api_result['encode_fps'],
                "constraints_count": api_result['constraints_count']
            }
        }
        
        metadata_file = os.path.join(output_dir, f'{base_filename}_metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"[OK] Metadata saved: {metadata_file}")
        
        print("=" * 80)
        print("[OK] TEAMS KPI ANALYSIS COMPLETE!")
        print("=" * 80)
        print(f"[FILE] Results saved to: {output_dir}")
        print(f"[FILE] Pickle file: {pickle_file}")
        print(f"[DATA] Result Keys: {len(api_result)} flat fields")
        print(f"[DATA] Constraints Data: {len(api_result['constraints_data'])} records")
        print("[OK] Compatible with speedlibs_service format!")
        
        return api_result
        
    except Exception as e:
        print(f"[ERROR] Error in Teams KPI analysis: {e}")
        import traceback
        traceback.print_exc()
        
        # Save error info
        error_file = os.path.join(output_dir, 'analysis_error.json')
        with open(error_file, 'w') as f:
            json.dump({
                "error": str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        return {
            "error": str(e),
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            "etl_file": etl_file_path
        }


def analyze_vcip_alignment(trace, time_range):
    """Simplified VCIP alignment analysis"""
    try:
        print(f"  [VCIP] Extracting events from {time_range[0]}s to {time_range[1]}s...")
        
        etl = trace.etl
        audio_events = []
        media_events = []
        ipu_events = []
        wlan_hw_events = []
        audio_hw_events = []
        
        # Extract regular events
        for ev in etl.get_events(time_range=time_range):
            timestamp_ms = ev["TimeStamp"] / 1000
            
            if 'AudioCore_Pump_GetCurrentPadding_Task' in ev[0] and 'win:Stop' in ev[0]:
                audio_events.append({'timestamp_ms': timestamp_ms})
            elif 'Decode_DDI_IP_Alignment' in ev[0] and 'win:Stop' in ev[0]:
                media_events.append({'timestamp_ms': timestamp_ms})
            elif 'Intel-Camera-Intel(R) AVStream Camera' in ev[0] and 'IP_ALIGNMENT' in ev[0]:
                ipu_events.append({'timestamp_ms': timestamp_ms})
        
        # Extract HW interrupts
        try:
            interrupts_df = trace.get_interrupts(time_range=time_range)
            
            audio_hw_df = interrupts_df[
                (interrupts_df['Name'].str.contains('intcaudiobus.sys', case=False, na=False)) &
                (interrupts_df['Type'].str.contains('HW', case=False, na=False))
            ]
            audio_hw_events = [{'timestamp_ms': t * 1000} for t in audio_hw_df['End(s)'].values]
            
            wlan_hw_df = interrupts_df[
                (interrupts_df['Name'].str.contains('netwaw16.sys', case=False, na=False)) &
                (interrupts_df['Type'].str.contains('HW', case=False, na=False))
            ]
            wlan_hw_events = [{'timestamp_ms': t * 1000} for t in wlan_hw_df['End(s)'].values]
        except Exception as e:
            print(f"  [VCIP] [WARNING] HW interrupt extraction failed: {e}")
        
        print(f"  [VCIP] Events: Audio={len(audio_events)}, Media={len(media_events)}, IPU={len(ipu_events)}")
        print(f"  [VCIP] HW: Audio={len(audio_hw_events)}, WLAN={len(wlan_hw_events)}")
        
        # Calculate alignments (simplified)
        media_rate = calculate_alignment_rate(media_events, audio_events, threshold_ms=2.0)
        ipu_rate = calculate_alignment_rate(ipu_events, audio_events, threshold_ms=2.0)
        wlan_rate = calculate_alignment_rate(wlan_hw_events, audio_hw_events, threshold_ms=2.5)
        
        missing_events = []
        if len(media_events) == 0:
            missing_events.append('Media')
        if len(ipu_events) == 0:
            missing_events.append('IPU')
        if len(wlan_hw_events) == 0:
            missing_events.append('WLAN HW')
        
        return {
            'media_to_audio': media_rate if media_rate is not None else 'NOT_FOUND',
            'ipu_to_audio': ipu_rate if ipu_rate is not None else 'NOT_FOUND',
            'wlan_to_audio': wlan_rate if wlan_rate is not None else 'NOT_FOUND',
            'audio_events_count': len(audio_events),
            'media_events_count': len(media_events),
            'ipu_events_count': len(ipu_events),
            'wlan_hw_events_count': len(wlan_hw_events),
            'audio_hw_events_count': len(audio_hw_events),
            'missing_events': missing_events
        }
        
    except Exception as e:
        print(f"  [VCIP] [FAIL] Error: {e}")
        return {'error': str(e)}


def analyze_teams_fps(trace, time_range):
    """Simplified Teams FPS analysis"""
    try:
        print(f"  [FPS] Extracting video events from {time_range[0]}s to {time_range[1]}s...")
        
        etl = trace.etl
        decoder_end_count = 0
        encode_count = 0
        vpblt_count = 0
        camera_count = 0
        
        for ev in etl.get_events(time_range=time_range):
            if 'ID3D11VideoContext_DecoderEndFrame' in ev[0] and 'win:Start' in ev[0]:
                decoder_end_count += 1
            if 'MFCaptureEngine-Sink-Task' in ev[0] and 'win:Start' in ev[0]:
                encode_count += 1
            if 'ID3D11VideoContext_VideoProcessorBlt' in ev[0] and 'win:Start' in ev[0]:
                vpblt_count += 1
            if 'MF_Devproxy_SendBuffersToDevice' in ev[0] and 'win:Start' in ev[0]:
                camera_count += 1
        
        decode_count = decoder_end_count - encode_count
        duration = time_range[1] - time_range[0]
        
        # Calculate FPS (following original logic)
        decode_fps = decode_count / duration / 9
        encode_fps = encode_count / duration
        vpblt_fps = vpblt_count / duration / 9
        camera_fps = camera_count / duration
        
        print(f"  [FPS] Decode={decode_fps:.2f}, Encode={encode_fps:.2f}, VPBLT={vpblt_fps:.2f}, Camera={camera_fps:.2f}")
        
        return {
            'decode_fps': round(decode_fps, 2),
            'encode_fps': round(encode_fps, 2),
            'vpblt_fps': round(vpblt_fps, 2),
            'camera_fps': round(camera_fps, 2),
            'decode_events_count': decode_count,
            'encode_events_count': encode_count,
            'vpblt_events_count': vpblt_count,
            'camera_events_count': camera_count
        }
        
    except Exception as e:
        print(f"  [FPS] [FAIL] Error: {e}")
        return {'error': str(e)}


def calculate_alignment_rate(source_events, target_events, threshold_ms):
    """Calculate alignment rate between source and target events"""
    if len(source_events) == 0 or len(target_events) == 0:
        return None
    
    aligned_count = 0
    
    for source_event in source_events:
        for target_event in target_events:
            delta = abs(source_event['timestamp_ms'] - target_event['timestamp_ms'])
            if delta <= threshold_ms:
                aligned_count += 1
                break
    
    rate = (aligned_count / len(source_events) * 100) if len(source_events) > 0 else 0.0
    return round(rate, 1)


def main():
    """Main entry point for standalone execution"""
    parser = argparse.ArgumentParser(
        description='Standalone Teams KPI Analysis (speed.exe compatible)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  speed.exe run standalone_teams_analysis.py --etl_file teams.etl --output_dir ./output
  speed.exe run standalone_teams_analysis.py --etl_file teams.etl --output_dir ./output --vcip_time_range 2,10
        """
    )
    
    parser.add_argument('--etl_file', required=True,
                       help='Path to ETL file to analyze')
    parser.add_argument('--output_dir', required=False, default=None,
                       help='Output directory for results (default: same directory as ETL file)')
    parser.add_argument('--time_range', default='0,60',
                       help='Main time range as "start,end" (default: 0,60)')
    parser.add_argument('--vcip_time_range', default='2,10',
                       help='VCIP time range as "start,end" (default: 2,10)')
    parser.add_argument('--fps_time_range', default='5,65',
                       help='FPS time range as "start,end" (default: 5,65)')
    parser.add_argument('--constraints_file',
                       default=DEFAULT_TEAMS_CONSTRAINT_FILE,
                       help='Path to Teams constraints file')
    
    args = parser.parse_args()
    
    # Parse time ranges
    def parse_range(range_str):
        parts = range_str.split(',')
        return (float(parts[0]), float(parts[1]))
    
    time_range = parse_range(args.time_range)
    vcip_time_range = parse_range(args.vcip_time_range)
    fps_time_range = parse_range(args.fps_time_range)
    
    # Validate inputs
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)
    
    # Run analysis
    results = run_teams_kpi_analysis(
        etl_file_path=args.etl_file,
        output_dir=args.output_dir,
        time_range=time_range,
        vcip_time_range=vcip_time_range,
        fps_time_range=fps_time_range,
        constraints_file=args.constraints_file
    )
    
    # Exit with appropriate code
    if results and 'error' not in results:
        print("\n[SUCCESS] Teams KPI analysis completed successfully")
        sys.exit(0)
    else:
        print("\n[FAILURE] Teams KPI analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
