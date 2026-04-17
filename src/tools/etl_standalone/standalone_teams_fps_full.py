"""
Custom Standalone: teams_fps_full
===================================
Full-trace FPS analysis for ms-teams.exe (PID 21200) using get_gpu_frames() and get_gpu_intervals(). Computes per-second FPS, frame time distribution (mean/std/percentiles), dropped frame detection (frame time > 2x median), and GPU activity summary.  Designed for Teams meeting quality analysis from OOB/CQP traces.

PKL: <etl_basename>_teams_fps_full.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.
"""
import sys, os, argparse, pickle
from datetime import datetime

import pandas as pd
import numpy as np
if not hasattr(np, "int"):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] {e}"); sys.exit(1)

PKL_SUFFIX = "teams_fps_full"


def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")


def run_analysis(trace, etl_file_path: str) -> dict:
    """User-provided analysis logic."""
    # SPEED event API:
    #   trace.get_events()                          — all events
    #   trace.get_events(event_types=["Prov/Evt"])  — filtered
    # Each item: ev["TimeStamp"], ev["EventName"], ev["ProcessId"], ev["<field>"]
    # Do NOT use speed.explorer or any other invented import.

    TARGET_PROCESS = "ms-teams.exe"
    TARGET_PID = 21200

    # ── 1. GPU Frames (Present/Flip events) for ms-teams.exe ────────────────────
    print(f"  Extracting GPU frames for {TARGET_PROCESS} (PID={TARGET_PID})...")
    try:
        df_frames_all = trace.os_trace.get_gpu_frames(process=TARGET_PROCESS)
        print(f"  get_gpu_frames returned {len(df_frames_all)} rows, cols: {list(df_frames_all.columns)}")
    except Exception as e:
        print(f"  get_gpu_frames failed: {e}")
        df_frames_all = pd.DataFrame()

    # Filter to target PID if multiple ms-teams.exe processes
    if not df_frames_all.empty and 'PID' in df_frames_all.columns:
        df_frames = df_frames_all[df_frames_all['PID'] == TARGET_PID].copy()
        print(f"  After PID={TARGET_PID} filter: {len(df_frames)} rows")
        if len(df_frames) == 0:
            # Fallback: use all ms-teams frames (any PID)
            df_frames = df_frames_all.copy()
            print(f"  PID filter removed all rows — using all {TARGET_PROCESS} frames: {len(df_frames)}")
    else:
        df_frames = df_frames_all.copy()

    # ── 2. Frame-time statistics ─────────────────────────────────────────────────
    if not df_frames.empty:
        start_col = next((c for c in ['Start(s)', 'start_s', 'Start'] if c in df_frames.columns), None)
        end_col   = next((c for c in ['End(s)',   'end_s',   'End']   if c in df_frames.columns), None)
        dur_col   = next((c for c in ['Duration(s)', 'duration_s', 'Duration'] if c in df_frames.columns), None)

        if start_col and end_col:
            trace_start = df_frames[start_col].min()
            trace_end   = df_frames[end_col].max()
            total_dur   = trace_end - trace_start
            total_frames = len(df_frames)
            avg_fps = total_frames / total_dur if total_dur > 0 else 0

            # Inter-frame intervals (time between successive frame starts = frame time)
            df_frames_sorted = df_frames.sort_values(start_col).copy()
            frame_times_ms = df_frames_sorted[start_col].diff().dropna() * 1000.0  # ms

            ft_mean   = frame_times_ms.mean()
            ft_std    = frame_times_ms.std()
            ft_median = frame_times_ms.median()
            ft_p5     = frame_times_ms.quantile(0.05)
            ft_p95    = frame_times_ms.quantile(0.95)
            ft_p99    = frame_times_ms.quantile(0.99)
            ft_min    = frame_times_ms.min()
            ft_max    = frame_times_ms.max()

            fps_from_ft = 1000.0 / ft_mean if ft_mean > 0 else 0

            # Per-second FPS (rolling 1-second window)
            df_frames_sorted['second_bucket'] = df_frames_sorted[start_col].apply(lambda t: int(t))
            fps_per_second = df_frames_sorted.groupby('second_bucket').size().reset_index()
            fps_per_second.columns = ['second', 'fps']
            fps_min  = fps_per_second['fps'].min()
            fps_max  = fps_per_second['fps'].max()
            fps_mean = fps_per_second['fps'].mean()
            fps_std  = fps_per_second['fps'].std()
            fps_p5   = fps_per_second['fps'].quantile(0.05)
            fps_p95  = fps_per_second['fps'].quantile(0.95)

            # Dropped frames: frame time > 2x median (glitch = > 3x median)
            drop_threshold   = ft_median * 2.0
            glitch_threshold = ft_median * 3.0
            dropped_frames  = (frame_times_ms > drop_threshold).sum()
            glitch_frames   = (frame_times_ms > glitch_threshold).sum()
            drop_pct        = dropped_frames / total_frames * 100 if total_frames > 0 else 0
            glitch_pct      = glitch_frames  / total_frames * 100 if total_frames > 0 else 0

            # Summary DataFrame
            df_teams_fps_full = pd.DataFrame([
                {'metric': 'Total Frames',           'value': total_frames,       'unit': 'frames'},
                {'metric': 'Trace Window',            'value': round(total_dur, 3),'unit': 's'},
                {'metric': 'Avg FPS (window)',        'value': round(avg_fps, 2),  'unit': 'fps'},
                {'metric': 'Avg FPS (from ft)',       'value': round(fps_from_ft, 2), 'unit': 'fps'},
                {'metric': 'FPS (per-sec) Min',       'value': fps_min,            'unit': 'fps'},
                {'metric': 'FPS (per-sec) Max',       'value': fps_max,            'unit': 'fps'},
                {'metric': 'FPS (per-sec) Mean',      'value': round(fps_mean, 2), 'unit': 'fps'},
                {'metric': 'FPS (per-sec) Std Dev',   'value': round(fps_std, 2),  'unit': 'fps'},
                {'metric': 'FPS (per-sec) P5',        'value': round(fps_p5, 2),   'unit': 'fps'},
                {'metric': 'FPS (per-sec) P95',       'value': round(fps_p95, 2),  'unit': 'fps'},
                {'metric': 'Frame Time Mean',         'value': round(ft_mean, 2),  'unit': 'ms'},
                {'metric': 'Frame Time Std Dev',      'value': round(ft_std, 2),   'unit': 'ms'},
                {'metric': 'Frame Time Median',       'value': round(ft_median, 2),'unit': 'ms'},
                {'metric': 'Frame Time Min',          'value': round(ft_min, 2),   'unit': 'ms'},
                {'metric': 'Frame Time Max',          'value': round(ft_max, 2),   'unit': 'ms'},
                {'metric': 'Frame Time P5',           'value': round(ft_p5, 2),    'unit': 'ms'},
                {'metric': 'Frame Time P95',          'value': round(ft_p95, 2),   'unit': 'ms'},
                {'metric': 'Frame Time P99',          'value': round(ft_p99, 2),   'unit': 'ms'},
                {'metric': 'Dropped Frames (>2x med)','value': int(dropped_frames),'unit': 'frames'},
                {'metric': 'Dropped %',               'value': round(drop_pct, 2), 'unit': '%'},
                {'metric': 'Glitch Frames (>3x med)', 'value': int(glitch_frames), 'unit': 'frames'},
                {'metric': 'Glitch %',                'value': round(glitch_pct, 2),'unit': '%'},
            ])
            print(f"  Stats computed: avg={avg_fps:.2f} fps, frames={total_frames}, dur={total_dur:.1f}s")
            print(f"  Frame time: mean={ft_mean:.2f}ms std={ft_std:.2f}ms p99={ft_p99:.2f}ms")
            print(f"  Dropped: {dropped_frames} ({drop_pct:.1f}%), Glitches: {glitch_frames} ({glitch_pct:.1f}%)")
        else:
            print(f"  WARNING: Missing Start/End columns. Available: {list(df_frames.columns)}")
            df_teams_fps_full = pd.DataFrame([{'metric': 'ERROR', 'value': 0, 'unit': 'Missing Start/End columns'}])
            fps_per_second = pd.DataFrame()
            df_frames_sorted = df_frames
    else:
        print(f"  NO GPU frames found for {TARGET_PROCESS}")
        df_teams_fps_full = pd.DataFrame([
            {'metric': 'Total Frames',    'value': 0, 'unit': 'frames'},
            {'metric': 'Status',          'value': 0, 'unit': 'NO_FRAMES_FOUND'},
        ])
        fps_per_second = pd.DataFrame()
        df_frames_sorted = pd.DataFrame()

    # ── 3. GPU Intervals for ms-teams.exe ────────────────────────────────────────
    print(f"  Extracting GPU intervals for {TARGET_PROCESS}...")
    try:
        df_gpu_int_all = trace.os_trace.get_gpu_intervals()
        if not df_gpu_int_all.empty and 'Process' in df_gpu_int_all.columns:
            df_gpu_int = df_gpu_int_all[
                df_gpu_int_all['Process'].str.lower().str.contains('ms-teams', na=False)
            ].copy()
            if df_gpu_int.empty and 'PID' in df_gpu_int_all.columns:
                df_gpu_int = df_gpu_int_all[df_gpu_int_all['PID'] == TARGET_PID].copy()
        else:
            df_gpu_int = df_gpu_int_all.copy()
        print(f"  GPU intervals for Teams: {len(df_gpu_int)} rows")
    except Exception as e:
        print(f"  get_gpu_intervals failed: {e}")
        df_gpu_int = pd.DataFrame()

    # Summarize GPU intervals by engine
    if not df_gpu_int.empty:
        dur_col_gi = next((c for c in ['Duration(s)', 'duration_s'] if c in df_gpu_int.columns), None)
        eng_col    = next((c for c in ['Engine', 'engine'] if c in df_gpu_int.columns), None)
        if eng_col and dur_col_gi:
            df_gpu_activity = df_gpu_int.groupby(eng_col).agg(
                count=(dur_col_gi, 'count'),
                total_s=(dur_col_gi, 'sum'),
                mean_ms=(dur_col_gi, lambda x: x.mean() * 1000),
                max_ms=(dur_col_gi, lambda x: x.max() * 1000),
            ).reset_index()
            df_gpu_activity.columns = ['Engine', 'Count', 'Total Duration(s)', 'Mean Duration(ms)', 'Max Duration(ms)']
        else:
            df_gpu_activity = pd.DataFrame({'info': [f'GPU intervals: {len(df_gpu_int)} rows, cols={list(df_gpu_int.columns)}']})
    else:
        df_gpu_activity = pd.DataFrame({'Engine': ['N/A'], 'Count': [0], 'Total Duration(s)': [0.0],
                                        'Mean Duration(ms)': [0.0], 'Max Duration(ms)': [0.0]})

    # Ensure output_key is assigned
    if 'df_teams_fps_full' not in dir():
        df_teams_fps_full = pd.DataFrame([{'metric': 'ERROR', 'value': 0, 'unit': 'script_failed'}])

    return {"df_teams_fps_full": df_teams_fps_full}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
    trace = tracedm.load_trace(etl_file=args.etl_file)
    data = run_analysis(trace, args.etl_file)
    data["meta"] = {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                     "timestamp": datetime.now().isoformat()}
    with open(pkl, "wb") as f:
        pickle.dump(data, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")


if __name__ == "__main__":
    main()
