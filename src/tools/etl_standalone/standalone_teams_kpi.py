"""
Standalone: teams_kpi
======================
Teams KPI analysis combining FPS, VCIP alignment, and pipeline (Media IP + Display IP) metrics.

Runs three analyses on the loaded trace:
  - VCIP alignment  : 4-IP alignment (Media/IPU/WLAN -> Audio)  time range 2-10 s
  - FPS             : Decode/Encode/VPBLT/Camera FPS             time range 5-65 s
  - Pipeline        : Media IP + Display IP detailed metrics      time range 32-33 s

PKL: <etl_basename>_teams_kpi.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Output DataFrames
-----------------
df_teams_fps       : metric / fps / event_count / status
df_vcip_alignment  : ip_pair / alignment_pct / aligned_events / total_events / threshold_ms / status
df_teams_pipeline  : layer / metric / fps / resolution / format / events

Raw dicts are also stored as raw_fps, raw_vcip, raw_pipeline for agent access to all fields.
"""
import sys
import os
import argparse
import pickle
from datetime import datetime

import pandas as pd
import numpy as np

if not hasattr(np, "int"):
    np.int = int
    np.float = float
    np.complex = complex
    np.bool = bool

try:
    import tracedm
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

PKL_SUFFIX = "teams_kpi"


def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")


# ===========================================================================
# VCIP 4-IP Alignment
# Source: VCIP_SingleETL_Enhanced from speedlibs_clean.py
# Adapted: etl_path_or_trace -> trace object only (standalone runner owns loading)
# ===========================================================================

class VCIP_SingleETL_Enhanced:
    """4-IP Audio-Centric Alignment Analysis (Media/IPU/WLAN -> Audio)"""

    def __init__(self):
        self.alignment_threshold_events = 2.0   # ms — regular events
        self.alignment_threshold_hw = 2.5        # ms — HW interrupts
        self.pass_threshold = 80.0               # % — PASS threshold

    def analyze_4ip_alignment(self, trace, time_range=(2, 10)):
        self.time_range = time_range
        try:
            events_results    = self._extract_all_events(trace)
            alignment_results = self._calculate_all_alignments_with_validation(events_results)
            return self._generate_final_assessment(alignment_results)
        except Exception as e:
            return {
                'error': str(e),
                'media_to_audio': 'ERROR',
                'ipu_to_audio':   'ERROR',
                'wlan_to_audio':  'ERROR',
                'overall_status': 'ERROR',
                'assessment': f'Analysis failed: {str(e)}'
            }

    def _extract_all_events(self, trace):
        etl = trace.etl
        audio_events, media_events, ipu_events = [], [], []

        print("[VCIP] Extracting events from ETL ...")
        for ev in etl.get_events(time_range=self.time_range):
            ts_ms = ev["TimeStamp"] / 1000
            if 'AudioCore_Pump_GetCurrentPadding_Task' in ev[0] and 'win:Stop' in ev[0]:
                audio_events.append({'timestamp_ms': ts_ms})
            elif 'Decode_DDI_IP_Alignment' in ev[0] and 'win:Stop' in ev[0]:
                media_events.append({'timestamp_ms': ts_ms})
            elif 'Intel-Camera-Intel(R) AVStream Camera' in ev[0] and 'IP_ALIGNMENT' in ev[0]:
                ipu_events.append({'timestamp_ms': ts_ms})

        audio_hw_events, wlan_hw_events = [], []
        hw_extraction_error = None
        try:
            interrupts_df = trace.get_interrupts(time_range=self.time_range)
            audio_hw_df = interrupts_df[
                interrupts_df['Name'].str.contains('intcaudiobus.sys', case=False, na=False) &
                interrupts_df['Type'].str.contains('HW', case=False, na=False)
            ]
            wlan_hw_df = interrupts_df[
                interrupts_df['Name'].str.contains('netwaw16.sys', case=False, na=False) &
                interrupts_df['Type'].str.contains('HW', case=False, na=False)
            ]
            audio_hw_events = [{'timestamp_ms': t * 1000} for t in audio_hw_df['End(s)'].values]
            wlan_hw_events  = [{'timestamp_ms': t * 1000} for t in wlan_hw_df['End(s)'].values]
        except Exception as e:
            hw_extraction_error = str(e)
            print(f"[VCIP] HW interrupt extraction failed: {e}")

        print(f"[VCIP] Audio={len(audio_events)}  Media={len(media_events)}  "
              f"IPU={len(ipu_events)}  AudioHW={len(audio_hw_events)}  WLAN={len(wlan_hw_events)}")
        return {
            'audio_events':       audio_events,
            'media_events':       media_events,
            'ipu_events':         ipu_events,
            'audio_hw_events':    audio_hw_events,
            'wlan_hw_events':     wlan_hw_events,
            'hw_extraction_error': hw_extraction_error
        }

    def _calculate_all_alignments_with_validation(self, er):
        def no_data(msg):
            return {'status': 'NOT_FOUND', 'message': msg,
                    'aligned_count': 0, 'rate': 'N/A', 'pairs': []}

        media_aln = (
            no_data('Media events not found in ETL'
                    if not er['media_events'] else 'Audio events not found in ETL')
            if not er['media_events'] or not er['audio_events']
            else {**self._calculate_alignment(er['media_events'], er['audio_events'],
                                              'media', self.alignment_threshold_events),
                  'status': 'CALCULATED',
                  'message': f"{len(er['media_events'])} Media events"}
        )

        ipu_aln = (
            no_data('IPU events not found in ETL'
                    if not er['ipu_events'] else 'Audio events not found in ETL')
            if not er['ipu_events'] or not er['audio_events']
            else {**self._calculate_alignment(er['ipu_events'], er['audio_events'],
                                              'ipu', self.alignment_threshold_events),
                  'status': 'CALCULATED',
                  'message': f"{len(er['ipu_events'])} IPU events"}
        )

        missing_hw = [s for s, lst in [('WLAN HW interrupts', er['wlan_hw_events']),
                                        ('Audio HW interrupts', er['audio_hw_events'])] if not lst]
        wlan_aln = (
            no_data(f"{' and '.join(missing_hw)} not found in ETL")
            if missing_hw
            else {**self._calculate_alignment(er['wlan_hw_events'], er['audio_hw_events'],
                                              'wlan', self.alignment_threshold_hw),
                  'status': 'CALCULATED',
                  'message': f"{len(er['wlan_hw_events'])} WLAN HW interrupts"}
        )

        missing_events = [n for n, lst in [
            ('Audio', er['audio_events']), ('Media', er['media_events']),
            ('IPU',   er['ipu_events']),   ('WLAN HW', er['wlan_hw_events']),
            ('Audio HW', er['audio_hw_events'])] if not lst]

        return {
            'events_counts': {k: len(er[k]) for k in
                              ['audio_events', 'media_events', 'ipu_events',
                               'audio_hw_events', 'wlan_hw_events']},
            'media_alignment': media_aln,
            'ipu_alignment':   ipu_aln,
            'wlan_alignment':  wlan_aln,
            'missing_events':  missing_events,
            'hw_extraction_error': er.get('hw_extraction_error')
        }

    def _calculate_alignment(self, source, target, name, threshold):
        aligned, pairs = 0, []
        for s in source:
            best_d = float('inf')
            for t in target:
                d = abs(s['timestamp_ms'] - t['timestamp_ms'])
                if d <= threshold and d < best_d:
                    best_d = d
            if best_d <= threshold:
                aligned += 1
                pairs.append({f'{name}_time': s['timestamp_ms'], 'delta': best_d})
        rate = (aligned / len(source) * 100) if source else 0.0
        return {
            'aligned_count': aligned,
            'rate': rate,
            'pairs': sorted(pairs, key=lambda x: x['delta'])[:5]
        }

    def _generate_final_assessment(self, ar):
        def rate_of(data):
            return data['rate'] if data['status'] == 'CALCULATED' else 'NOT_FOUND'

        m_rate = rate_of(ar['media_alignment'])
        i_rate = rate_of(ar['ipu_alignment'])
        w_rate = rate_of(ar['wlan_alignment'])

        calc = [r for r in [m_rate, i_rate, w_rate] if isinstance(r, (int, float))]
        pass_count = sum(1 for r in calc if r >= self.pass_threshold)

        if not calc:
            overall, assessment = 'NO_DATA', 'No IP events found for alignment analysis'
        elif pass_count == len(calc) == 3:
            overall, assessment = 'PASS', 'All IPs achieve excellent alignment (>=80%)'
        elif pass_count >= len(calc) * 0.67:
            overall, assessment = ('MARGINAL',
                                   f'{pass_count}/{len(calc)} available IPs achieve good alignment (>=80%)')
        else:
            overall, assessment = ('FAIL',
                                   f'Only {pass_count}/{len(calc)} available IPs achieve acceptable alignment')

        if ar['missing_events']:
            assessment += f" | Missing: {', '.join(ar['missing_events'])}"

        return {
            'media_to_audio':     round(m_rate, 1) if isinstance(m_rate, float) else m_rate,
            'ipu_to_audio':       round(i_rate, 1) if isinstance(i_rate, float) else i_rate,
            'wlan_to_audio':      round(w_rate, 1) if isinstance(w_rate, float) else w_rate,
            'overall_status':     overall,
            'pass_count':         pass_count,
            'calculated_count':   len(calc),
            'assessment':         assessment,
            'missing_events':     ar['missing_events'],
            'alignment_details':  ar
        }


# ===========================================================================
# Teams FPS
# Source: TeamsFPS from speedlibs_clean.py
# Adapted: etl_path_or_trace -> trace object only
# ===========================================================================

class TeamsFPS:
    """Teams Video Pipeline FPS Analysis (Decode/Encode/VPBLT/Camera)"""

    def analyze_fps(self, trace, time_range=(5, 65)):
        self.time_range = time_range
        try:
            events_data = self._extract_video_events(trace, time_range)
            fps_results  = self._calculate_fps_metrics(events_data, time_range)
            return self._generate_fps_results(fps_results, time_range)
        except Exception as e:
            return {'error': str(e), 'decode_fps': 0.0, 'encode_fps': 0.0,
                    'vpblt_fps': 0.0, 'camera_fps': 0.0, 'status': 'ERROR'}

    def _extract_video_events(self, trace, time_range):
        start, end = time_range
        print(f"[FPS] Extracting video events {start}s - {end}s ...")
        etl = trace.etl
        decoder_end_count = encode_count = vpblt_count = camera_count = 0

        for ev in etl.get_events(time_range=self.time_range):
            if 'ID3D11VideoContext_DecoderEndFrame'   in ev[0] and 'win:Start' in ev[0]:
                decoder_end_count += 1
            if 'MFCaptureEngine-Sink-Task'            in ev[0] and 'win:Start' in ev[0]:
                encode_count += 1
            if 'ID3D11VideoContext_VideoProcessorBlt' in ev[0] and 'win:Start' in ev[0]:
                vpblt_count += 1
            if 'MF_Devproxy_SendBuffersToDevice'      in ev[0] and 'win:Start' in ev[0]:
                camera_count += 1

        decode_count = decoder_end_count - encode_count
        print(f"[FPS] DecoderEnd={decoder_end_count}  Encode={encode_count}  "
              f"Decode={decode_count}  VPBLT={vpblt_count}  Camera={camera_count}")
        return {
            'decoder_end_count': decoder_end_count,
            'encode_count':      encode_count,
            'decode_count':      decode_count,
            'vpblt_count':       vpblt_count,
            'camera_count':      camera_count
        }

    def _calculate_fps_metrics(self, events_data, time_range):
        duration = time_range[1] - time_range[0]
        return {
            'decode_fps':  events_data['decode_count']  / duration / 9,
            'encode_fps':  events_data['encode_count']  / duration,
            'vpblt_fps':   events_data['vpblt_count']   / duration / 9,
            'camera_fps':  events_data['camera_count']  / duration,
            'duration':    duration,
            'events_data': events_data
        }

    def _generate_fps_results(self, fps_results, time_range):
        ed = fps_results['events_data']
        return {
            'decode_fps':  round(fps_results['decode_fps'],  2),
            'encode_fps':  round(fps_results['encode_fps'],  2),
            'vpblt_fps':   round(fps_results['vpblt_fps'],   2),
            'camera_fps':  round(fps_results['camera_fps'],  2),
            'time_range':  time_range,
            'duration':    fps_results['duration'],
            'event_counts': {
                'decode_events':      ed['decode_count'],
                'encode_events':      ed['encode_count'],
                'vpblt_events':       ed['vpblt_count'],
                'camera_events':      ed['camera_count'],
                'decoder_end_events': ed['decoder_end_count']
            },
            'status': 'SUCCESS'
        }


# ===========================================================================
# Teams Pipeline Analysis (Media IP + Display IP)
# Source: TeamsPipelineAnalysis from speedlibs_clean.py
# Adapted: etl_path_or_trace -> trace object only
# ===========================================================================

class TeamsPipelineAnalysis:
    """Teams Video Pipeline Detailed Analysis — Media IP and Display IP metrics"""

    def __init__(self):
        self.format_mapping = {25: "NV12", 1: "ARGB8", 4: "H264"}
        self.present_mode_names = {
            0: "D3DKMT_PM_UNINITIALIZED",
            1: "D3DKMT_PM_REDIRECTED_GDI",
            2: "D3DKMT_PM_REDIRECTED_FLIP",
            3: "D3DKMT_PM_REDIRECTED_BLT",
            4: "D3DKMT_PM_REDIRECTED_VISTABLT",
            5: "D3DKMT_PM_SCREENCAPTUREFENCE",
            6: "D3DKMT_PM_REDIRECTED_GDI_SYSMEM",
            7: "D3DKMT_PM_REDIRECTED_COMPOSITION"
        }

    def analyze_pipeline(self, trace, time_range=(32, 33)):
        try:
            events_data = self._extract_pipeline_events(trace, time_range)
            metrics      = self._calculate_pipeline_metrics(events_data, time_range)
            return self._generate_pipeline_results(metrics, time_range)
        except Exception as e:
            return {'error': str(e), 'status': 'ERROR'}

    def _extract_pipeline_events(self, trace, time_range):
        start, end = time_range
        duration = end - start
        print(f"[PIPELINE] Extracting Media IP + Display IP events {start}s - {end}s ...")
        etl = trace.etl

        # ── Media IP counters ─────────────────────────────────────────────────
        osD3D_Decoder = 0
        imed_DecodePicture_DecodeFPS = imed_DecodePicture_DecodeWidth = 0
        imed_DecodePicture_DecodeHeight = imed_DecodePicture_DecodeFormat = 0
        imed_DecodePicture_DecodeBitdepth = 0
        camera_count = isubID0_720count = isubID0_240count = 0
        imed_VPBlt_encHeight = imed_VPBlt_encwidth = imed_VPBlt_encFormat = 0
        imed_VPBlt_inHeight  = imed_VPBlt_inwidth  = imed_VPBlt_inFormat  = 0
        imed_VPBlt_outHeight = imed_VPBlt_outwidth = imed_VPBlt_outFormat = 0

        # ── Display IP counters ───────────────────────────────────────────────
        osDxg_Presentcnt = os_present_mode = 0
        os_Present_srcRectW = os_Present_srcRectH = 0
        os_Present_destRectW = os_Present_destRectH = 0
        osMMIOMPO_cnt = osVSyncInterrupt = igd_Vbicnt = igd_FlipQExec_Cnt = 0

        # Decode OS
        for ev in etl.get_events(
                event_types=['Microsoft-Windows-Direct3D11/ID3D11VideoContext_DecoderBeginFrame/win:Start'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                osD3D_Decoder += 1

        # Decode Driver
        for ev in etl.get_events(
                event_types=['Intel-Media/Decode_Info_Picture/win:Info'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                imed_DecodePicture_DecodeFPS   += 1
                imed_DecodePicture_DecodeWidth  = ev['Width']
                imed_DecodePicture_DecodeHeight = ev['Height']
                imed_DecodePicture_DecodeFormat = ev['CodecFormat']
                imed_DecodePicture_DecodeBitdepth = ev['Bitdepth']

        # Encode OS
        for ev in etl.get_events(
                event_types=['Microsoft-Windows-MF/MF_Devproxy_SendBuffersToDevice/win:Start'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                camera_count += 1

        # Encode + VPBlt Driver
        for ev in etl.get_events(
                event_types=['Intel-Media/eDDI_VP_Blt/win:Info'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                imed_VPBlt_outHeight = ev['oHeight']
                imed_VPBlt_outwidth  = ev['oWidth']
                imed_VPBlt_outFormat = ev['oFormat']
                if ev['iHeight'] == 720:
                    isubID0_720count    += 1
                    imed_VPBlt_encHeight = ev['iHeight']
                    imed_VPBlt_encwidth  = ev['iWidth']
                    imed_VPBlt_encFormat = ev['iFormat']
                if ev['iHeight'] == 240:
                    isubID0_240count   += 1
                    imed_VPBlt_inHeight  = ev['iHeight']
                    imed_VPBlt_inwidth   = ev['iWidth']
                    imed_VPBlt_inFormat  = ev['iFormat']

        # Display Present OS
        for ev in etl.get_events(
                event_types=['Microsoft-Windows-DxgKrnl/PresentHistoryDetailed/win:Start'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                osDxg_Presentcnt     += 1
                os_present_mode       = ev['Model']
                os_Present_srcRectW   = ev['SourceRect.right']
                os_Present_srcRectH   = ev['SourceRect.bottom']
                os_Present_destRectW  = ev['DestWidth']
                os_Present_destRectH  = ev['DestHeight']

        # MMIOFlip OS
        for ev in etl.get_events(
                event_types=['Microsoft-Windows-DxgKrnl/MMIOFlipMultiPlaneOverlay/win:Info'],
                time_range=time_range):
            if 'System' in ev['Process Name']:
                osMMIOMPO_cnt += 1

        # VSync OS
        for ev in etl.get_events(
                event_types=['Microsoft-Windows-DxgKrnl/VSyncInterrupt/win:Info'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                osVSyncInterrupt += 1

        # VBlank Driver
        for ev in etl.get_events(
                event_types=['Intel-Gfx-Driver-Display/VBlankInterrupt/PipeA'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                igd_Vbicnt += 1

        # FlipQ Driver
        for ev in etl.get_events(
                event_types=['Intel-Gfx-Driver-Display/FlipQExecuted/Info'],
                time_range=time_range):
            if 'ms-teams.exe' in ev['Process Name']:
                igd_FlipQExec_Cnt += 1

        print(f"[PIPELINE] DecodeOS={osD3D_Decoder}  DecodeDrv={imed_DecodePicture_DecodeFPS}  "
              f"EncodeOS={camera_count}  Present={osDxg_Presentcnt}  "
              f"MMIOFlip={osMMIOMPO_cnt}  VSync={osVSyncInterrupt}")

        return {
            'duration': duration,
            # Media decode
            'media_decode_os_count':   osD3D_Decoder,
            'media_decode_drv_count':  imed_DecodePicture_DecodeFPS,
            'decode_width':            imed_DecodePicture_DecodeWidth,
            'decode_height':           imed_DecodePicture_DecodeHeight,
            'decode_format':           imed_DecodePicture_DecodeFormat,
            'decode_bitdepth':         imed_DecodePicture_DecodeBitdepth,
            # Media encode
            'media_encode_os_count':   camera_count,
            'media_encode_drv_count':  isubID0_720count,
            'encode_width':            imed_VPBlt_encwidth,
            'encode_height':           imed_VPBlt_encHeight,
            'encode_format':           imed_VPBlt_encFormat,
            # VPBlt
            'vpblt_input_count':       isubID0_240count,
            'vpblt_input_width':       imed_VPBlt_inwidth,
            'vpblt_input_height':      imed_VPBlt_inHeight,
            'vpblt_input_format':      imed_VPBlt_inFormat,
            'vpblt_output_width':      imed_VPBlt_outwidth,
            'vpblt_output_height':     imed_VPBlt_outHeight,
            'vpblt_output_format':     imed_VPBlt_outFormat,
            # Display
            'display_present_count':   osDxg_Presentcnt,
            'display_present_mode':    os_present_mode,
            'display_source_width':    os_Present_srcRectW,
            'display_source_height':   os_Present_srcRectH,
            'display_dest_width':      os_Present_destRectW,
            'display_dest_height':     os_Present_destRectH,
            'display_mmioflip_count':  osMMIOMPO_cnt,
            'display_vsync_count':     osVSyncInterrupt,
            'display_vblank_count':    igd_Vbicnt,
            'display_flipq_count':     igd_FlipQExec_Cnt
        }

    def _get_format_name(self, code):
        return self.format_mapping.get(code, f"UNKNOWN({code})")

    def _calculate_pipeline_metrics(self, ed, time_range):
        dur = ed['duration']
        return {
            # Media IP
            'media_decode_os_fps':      round(ed['media_decode_os_count']  / dur / 9, 2),
            'media_decode_drv_fps':     round(ed['media_decode_drv_count'] / dur / 9, 2),
            'media_decode_resolution':  f"{ed['decode_width']}x{ed['decode_height']}",
            'media_decode_format':      'H264' if ed['decode_format'] == 4 else 'MJPEG',
            'media_decode_bitdepth':    ed['decode_bitdepth'],
            'media_encode_os_fps':      ed['media_encode_os_count'],
            'media_encode_drv_fps':     round(ed['media_encode_drv_count'] / dur, 2),
            'media_encode_resolution':  f"{ed['encode_width']}x{ed['encode_height']}",
            'media_encode_format':      self._get_format_name(ed['encode_format']),
            'vpblt_input_fps':          ed['vpblt_input_count'],
            'vpblt_input_resolution':   f"{ed['vpblt_input_width']}x{ed['vpblt_input_height']}",
            'vpblt_input_format':       self._get_format_name(ed['vpblt_input_format']),
            'vpblt_output_resolution':  f"{ed['vpblt_output_width']}x{ed['vpblt_output_height']}",
            'vpblt_output_format':      self._get_format_name(ed['vpblt_output_format']),
            # Display IP
            'display_present_fps':      round(ed['display_present_count'] / dur, 2),
            'display_present_mode':     self.present_mode_names.get(
                                            ed['display_present_mode'],
                                            f"Unknown({ed['display_present_mode']})"),
            'display_source_resolution': f"{ed['display_source_width']}x{ed['display_source_height']}",
            'display_dest_resolution':   f"{ed['display_dest_width']}x{ed['display_dest_height']}",
            'display_mmioflip_fps':     round(ed['display_mmioflip_count'] / dur, 2),
            'display_vsync_fps':        round(ed['display_vsync_count']   / dur, 2),
            'display_vblank_fps':       round(ed['display_vblank_count']  / dur, 2),
            'display_flipq_fps':        round(ed['display_flipq_count']   / dur, 2),
            'event_counts': ed
        }

    def _generate_pipeline_results(self, metrics, time_range):
        ed = metrics['event_counts']
        result = {k: v for k, v in metrics.items() if k != 'event_counts'}
        result.update({
            'media_decode_os_events':   ed['media_decode_os_count'],
            'media_decode_drv_events':  ed['media_decode_drv_count'],
            'media_encode_os_events':   ed['media_encode_os_count'],
            'media_encode_drv_events':  ed['media_encode_drv_count'],
            'display_present_events':   ed['display_present_count'],
            'display_mmioflip_events':  ed['display_mmioflip_count'],
            'display_vsync_events':     ed['display_vsync_count'],
            'display_vblank_events':    ed['display_vblank_count'],
            'display_flipq_events':     ed['display_flipq_count'],
            'time_range': time_range,
            'status': 'SUCCESS'
        })
        return result


# ===========================================================================
# Main analysis entry point
# ===========================================================================

def run_analysis(trace, etl_file_path: str) -> dict:
    """
    Run all three Teams KPI analyses on an already-loaded trace.

    Returns a dict containing:
      df_teams_fps       — FPS summary DataFrame
      df_vcip_alignment  — 4-IP alignment DataFrame
      df_teams_pipeline  — Media IP + Display IP DataFrame
      raw_fps            — full dict from TeamsFPS
      raw_vcip           — full dict from VCIP_SingleETL_Enhanced
      raw_pipeline       — full dict from TeamsPipelineAnalysis
    """
    print("[TEAMS-KPI] === VCIP alignment (2-10 s) ===")
    vcip_raw = VCIP_SingleETL_Enhanced().analyze_4ip_alignment(trace, time_range=(2, 10))

    print("[TEAMS-KPI] === FPS analysis (5-65 s) ===")
    fps_raw = TeamsFPS().analyze_fps(trace, time_range=(5, 65))

    print("[TEAMS-KPI] === Pipeline analysis (32-33 s) ===")
    pipeline_raw = TeamsPipelineAnalysis().analyze_pipeline(trace, time_range=(32, 33))

    # ── df_teams_fps ──────────────────────────────────────────────────────────
    ec = fps_raw.get('event_counts', {})
    df_teams_fps = pd.DataFrame([
        {'metric': 'decode_fps',  'fps': fps_raw.get('decode_fps',  0.0),
         'event_count': ec.get('decode_events',  0), 'status': fps_raw.get('status', 'ERROR')},
        {'metric': 'encode_fps',  'fps': fps_raw.get('encode_fps',  0.0),
         'event_count': ec.get('encode_events',  0), 'status': fps_raw.get('status', 'ERROR')},
        {'metric': 'vpblt_fps',   'fps': fps_raw.get('vpblt_fps',   0.0),
         'event_count': ec.get('vpblt_events',   0), 'status': fps_raw.get('status', 'ERROR')},
        {'metric': 'camera_fps',  'fps': fps_raw.get('camera_fps',  0.0),
         'event_count': ec.get('camera_events',  0), 'status': fps_raw.get('status', 'ERROR')},
    ])

    # ── df_vcip_alignment ─────────────────────────────────────────────────────
    ad = vcip_raw.get('alignment_details', {})
    cnt = ad.get('events_counts', {})
    df_vcip_alignment = pd.DataFrame([
        {'ip_pair': 'Media -> Audio',
         'alignment_pct':  vcip_raw.get('media_to_audio'),
         'aligned_events': ad.get('media_alignment', {}).get('aligned_count', 0),
         'total_events':   cnt.get('media_events', 0),
         'threshold_ms': 2.0,
         'status': ad.get('media_alignment', {}).get('status', 'UNKNOWN')},
        {'ip_pair': 'IPU -> Audio',
         'alignment_pct':  vcip_raw.get('ipu_to_audio'),
         'aligned_events': ad.get('ipu_alignment', {}).get('aligned_count', 0),
         'total_events':   cnt.get('ipu_events', 0),
         'threshold_ms': 2.0,
         'status': ad.get('ipu_alignment', {}).get('status', 'UNKNOWN')},
        {'ip_pair': 'WLAN -> Audio',
         'alignment_pct':  vcip_raw.get('wlan_to_audio'),
         'aligned_events': ad.get('wlan_alignment', {}).get('aligned_count', 0),
         'total_events':   cnt.get('wlan_hw_events', 0),
         'threshold_ms': 2.5,
         'status': ad.get('wlan_alignment', {}).get('status', 'UNKNOWN')},
    ])

    # ── df_teams_pipeline ─────────────────────────────────────────────────────
    pr = pipeline_raw
    df_teams_pipeline = pd.DataFrame([
        # Media IP
        {'layer': 'Media',   'metric': 'Decode (OS)',
         'fps': pr.get('media_decode_os_fps'),   'resolution': pr.get('media_decode_resolution'),
         'format': pr.get('media_decode_format'), 'events': pr.get('media_decode_os_events')},
        {'layer': 'Media',   'metric': 'Decode (Driver)',
         'fps': pr.get('media_decode_drv_fps'),  'resolution': pr.get('media_decode_resolution'),
         'format': pr.get('media_decode_format'), 'events': pr.get('media_decode_drv_events')},
        {'layer': 'Media',   'metric': 'Encode (OS)',
         'fps': pr.get('media_encode_os_fps'),   'resolution': pr.get('media_encode_resolution'),
         'format': pr.get('media_encode_format'), 'events': pr.get('media_encode_os_events')},
        {'layer': 'Media',   'metric': 'Encode (Driver)',
         'fps': pr.get('media_encode_drv_fps'),  'resolution': pr.get('media_encode_resolution'),
         'format': pr.get('media_encode_format'), 'events': pr.get('media_encode_drv_events')},
        {'layer': 'Media',   'metric': 'VPBlt Input',
         'fps': pr.get('vpblt_input_fps'),        'resolution': pr.get('vpblt_input_resolution'),
         'format': pr.get('vpblt_input_format'),  'events': None},
        # Display IP
        {'layer': 'Display', 'metric': 'Present',
         'fps': pr.get('display_present_fps'),   'resolution': pr.get('display_source_resolution'),
         'format': pr.get('display_present_mode'), 'events': pr.get('display_present_events')},
        {'layer': 'Display', 'metric': 'MMIOFlip',
         'fps': pr.get('display_mmioflip_fps'),  'resolution': None,
         'format': None,                           'events': pr.get('display_mmioflip_events')},
        {'layer': 'Display', 'metric': 'VSync',
         'fps': pr.get('display_vsync_fps'),     'resolution': None,
         'format': None,                           'events': pr.get('display_vsync_events')},
        {'layer': 'Display', 'metric': 'VBlank (Driver)',
         'fps': pr.get('display_vblank_fps'),    'resolution': None,
         'format': None,                           'events': pr.get('display_vblank_events')},
        {'layer': 'Display', 'metric': 'FlipQ (Driver)',
         'fps': pr.get('display_flipq_fps'),     'resolution': None,
         'format': None,                           'events': pr.get('display_flipq_events')},
    ])

    return {
        'df_teams_fps':      df_teams_fps,
        'df_vcip_alignment': df_vcip_alignment,
        'df_teams_pipeline': df_teams_pipeline,
        'raw_fps':           fps_raw,
        'raw_vcip':          vcip_raw,
        'raw_pipeline':      pipeline_raw,
    }


def main():
    ap = argparse.ArgumentParser(description="Teams KPI standalone — FPS + VCIP + Pipeline")
    ap.add_argument("--etl_file",   required=True,  help="Path to ETL file")
    ap.add_argument("--output_dir", required=False, default=None,
                    help="Output directory (unused; PKL is written beside the ETL)")
    args = ap.parse_args()

    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE] PKL already exists: {pkl}")
        sys.exit(0)

    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)

    print(f"[TEAMS-KPI] Loading trace: {args.etl_file}")
    trace = load_trace(etl_file=args.etl_file)

    results = run_analysis(trace, args.etl_file)

    meta = {
        "etl_file":   args.etl_file,
        "pkl_suffix": PKL_SUFFIX,
        "created_at": datetime.now().isoformat(),
        "analyses":   ["vcip(2-10s)", "fps(5-65s)", "pipeline(32-33s)"]
    }

    with open(pkl, "wb") as fh:
        pickle.dump({**results, "meta": meta}, fh)

    print(f"[PKL] Saved -> {pkl}")
    sys.exit(0)


if __name__ == "__main__":
    main()
