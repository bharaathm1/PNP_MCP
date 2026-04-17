"""Profile compile_power_data cache-hit path step by step."""
import time, sys, os, csv, re
sys.path.insert(0, r'c:\pnp_mcp\src')
sys.path.insert(0, r'c:\pnp_mcp')
from pathlib import Path

FOLDER = r'\\gar.corp.intel.com\ec\proj\my\ccg\WCL_PnP\Debug\Demo_CQP_OOB'
folder = Path(FOLDER)
output_dir = folder / 'Analysis' / 'power_output'
csv_final  = output_dir / 'Power_output_summary_final.csv'
md_path    = output_dir / 'Power_output_summary_final_markdown.txt'

# Step 1: the actual cache guard check
t0 = time.perf_counter()
exists = md_path.exists()
t1 = time.perf_counter()
print(f'md_path.exists():                 {(t1-t0)*1000:7.1f} ms   result={exists}')

if exists:
    t2 = time.perf_counter()
    size = md_path.stat().st_size
    t3 = time.perf_counter()
    print(f'md_path.stat().st_size:           {(t3-t2)*1000:7.1f} ms   size={size}')

# Step 2: CSV read (for _build_tiered_response)
t4 = time.perf_counter()
exists_csv = csv_final.exists()
t5 = time.perf_counter()
print(f'csv_final.exists():               {(t5-t4)*1000:7.1f} ms   result={exists_csv}')

if exists_csv:
    t6 = time.perf_counter()
    with open(csv_final, 'r', newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        fns = reader.fieldnames or []
        col_names = [c for c in fns[1:] if c]
        rail_count = sum(1 for _ in reader)
    t7 = time.perf_counter()
    print(f'open+read CSV ({rail_count} rails):       {(t7-t6)*1000:7.1f} ms')

    # Step 3: group columns
    t8 = time.perf_counter()
    groups = {}
    for col in col_names:
        m = re.match(r'\d{8}T\d{6}-(.*)', col)
        base = m.group(1) if m else col
        base = re.sub(r'_R\d+[A-Za-z]*$', '', base)
        groups.setdefault(base, []).append(col)
    kpi = sorted(groups.keys())
    t9 = time.perf_counter()
    print(f'group KPI columns ({len(kpi)} kpis):     {(t9-t8)*1000:7.1f} ms   kpis={kpi}')

# Step 4: import cost (one-time module import tax)
t10 = time.perf_counter()
import tools.power_tools as pt
t11 = time.perf_counter()
print(f'import tools.power_tools:         {(t11-t10)*1000:7.1f} ms')

t12 = time.perf_counter()
import tools.socwatch_tools as st
t13 = time.perf_counter()
print(f'import tools.socwatch_tools:      {(t13-t12)*1000:7.1f} ms')
