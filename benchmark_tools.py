"""
Standalone benchmark — measures per-tool execution time and response size
for the exact sequence the power_socwatch_analysis agent runs for:
  "I have power logs here: Demo_CQP_OOB — summarize the power rails"

Run from repo root:
    python benchmark_tools.py
"""
import time
import json
import sys
import os
import csv
import re

# ── path setup (mirror what the MCP server does) ─────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "src")
sys.path.insert(0, ROOT)
sys.path.insert(0, SRC)

FOLDER = r"\\gar.corp.intel.com\ec\proj\my\ccg\WCL_PnP\Debug\Demo_CQP_OOB"

# ── import underlying logic directly (bypass @mcp.tool wrapper) ───────────────
# We import the module-level helpers, not the FunctionTool objects.

# --- knowledge tool ---
from tools.power_rail_knowledge_tools import (
    _load_all_rails, _get_collection, _prepare_document, _ensure_indexes
)

# --- power pipeline (only what we actually call inline) ---
from tools.power_tools import _find_summary_csvs, _can_read_file

# --- SocWatch pipeline ---
from tools.socwatch_tools import (
    _extract_sections_from_md,
)

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
SEP = "-" * 72

def report(label, elapsed, resp_bytes):
    tokens_approx = resp_bytes // 4
    print(f"  {label:<42} {elapsed*1000:7.1f} ms   {resp_bytes:>7,} chars  ~{tokens_approx:>5,} tok")


# ─────────────────────────────────────────────────────────────────────────────
# 1. load_power_rail_knowledge_to_mongodb  (inline)
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("BENCHMARK — power_socwatch_analysis agent tool sequence")
print(SEP)

from config.settings import settings as _settings   # ensure config importable

_MONGO_DB         = "pnp_database"
_MONGO_COLLECTION = "power_rail_knowledge"

t0 = time.perf_counter()
try:
    collection = _get_collection()
    raw_docs = _load_all_rails()
    upserted = 0
    for raw in raw_docs:
        if raw.get("name"):
            from tools.power_rail_knowledge_tools import _prepare_document
            rt = raw.pop("_rail_type", "soc")
            doc = _prepare_document(raw, rt)
            existing = collection.find_one({"name": doc["name"]})
            if existing:
                collection.replace_one({"name": doc["name"]}, doc)
            else:
                collection.insert_one(doc)
            upserted += 1
    _ensure_indexes(collection)
    result_kb = {"success": True, "upserted": upserted,
                 "total_documents": collection.count_documents({})}
except Exception as e:
    result_kb = {"success": False, "error": str(e)}
t1 = time.perf_counter()

resp_kb = json.dumps(result_kb)
report("load_power_rail_knowledge_to_mongodb", t1 - t0, len(resp_kb))


# ─────────────────────────────────────────────────────────────────────────────
# 2. compile_power_data  (cached path — Analysis/ already exists)
# ─────────────────────────────────────────────────────────────────────────────
import re as _re_module

t2 = time.perf_counter()
folder = Path(FOLDER)
output_dir = folder / "Analysis" / "power_output"
md_path    = output_dir / "Power_output_summary_final_markdown.txt"
csv_final  = output_dir / "Power_output_summary_final.csv"

kpi_groups_grouped = []
rail_count = 0
if csv_final.exists():
    with open(csv_final, "r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fns = reader.fieldnames or []
        col_names = [c for c in fns[1:] if c]
        rail_count = sum(1 for _ in reader)
    groups = {}
    for col in col_names:
        m = _re_module.match(r"\d{8}T\d{6}-(.*)", col)
        base = m.group(1) if m else col
        base = _re_module.sub(r"_R\d+[A-Za-z]*$", "", base)
        groups.setdefault(base, []).append(col)
    kpi_groups_grouped = sorted(groups.keys())

result_compile = {
    "success": True,
    "cached": True,
    "rail_count": rail_count,
    "kpi_names": kpi_groups_grouped,
    "kpi_groups": len(kpi_groups_grouped),
    "message": f"Pipeline loaded from cache. {rail_count} rails x {len(kpi_groups_grouped)} KPI groups."
}
t3 = time.perf_counter()
resp_compile = json.dumps(result_compile)
report("compile_power_data (cache hit)", t3 - t2, len(resp_compile))


# ─────────────────────────────────────────────────────────────────────────────
# 3. parse_socwatch_data  (cached path)
# ─────────────────────────────────────────────────────────────────────────────
t4 = time.perf_counter()
sw_md = folder / "Analysis" / "socwatch_output" / "socwatch_output_summary.md"
section_names = []
if sw_md.exists():
    md_text = sw_md.read_text(encoding="utf-8")
    section_names = list(_extract_sections_from_md(md_text).keys())

result_parse = {
    "success": True,
    "cached": True,
    "section_names": section_names,
    "section_count": len(section_names),
    "message": f"Pipeline loaded from cache. {len(section_names)} sections available."
}
t5 = time.perf_counter()
resp_parse = json.dumps(result_parse)
report("parse_socwatch_data (cache hit)", t5 - t4, len(resp_parse))


# ─────────────────────────────────────────────────────────────────────────────
# 4. query_power_matrix (rails=None — uses new 20-rail cap)
# ─────────────────────────────────────────────────────────────────────────────
_PRIORITY = [
    "P_SOC", "P_CPU_TOTAL", "P_CPU_PCH_TOTAL",
    "P_MEMORY", "P_DISPLAY", "P_BACKLIGHT", "P_SSD", "P_WLAN",
    "VCC_LP_ECORE", "VCCCORE", "VCCSA", "VCCGT",
    "VCCPRIM_IO", "VDD2_CPU", "VCCST", "VCCPRIM_VNNAON",
    "P_VCCCORE", "P_VCC_LP_ECORE", "P_VCCSA", "P_VCCGT",
    "P_VAL_VCC_LP", "P_VAL_VCCCORE", "P_VAL_VCCSA", "P_VAL_VCCGT",
    "P_VBATA", "VBATA",
]

t6 = time.perf_counter()
matrix = {}
row_order = []
col_names_m = []
if csv_final.exists():
    with open(csv_final, "r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fns = reader.fieldnames or []
        rail_col = fns[0] if fns else "Rail"
        col_names_m = [c for c in fns[1:] if c]
        for row in reader:
            rail = (row.get(rail_col) or "").strip()
            if not rail:
                continue
            row_order.append(rail)
            vals = {}
            for c in col_names_m:
                v = (row.get(c) or "").strip()
                try:
                    vals[c] = float(v)
                except ValueError:
                    pass
            matrix[rail] = vals

# group columns
groups_m = {}
for col in col_names_m:
    m = _re_module.match(r"\d{8}T\d{6}-(.*)", col)
    base = m.group(1) if m else col
    base = _re_module.sub(r"_R\d+[A-Za-z]*$", "", base)
    groups_m.setdefault(base, []).append(col)

# priority sort + 20-rail cap
_MAX_RAILS = 20
ordered = []
for p in _PRIORITY:
    for r in row_order:
        if r not in ordered and (r.lower().startswith(p.lower()) or r.lower() == p.lower()):
            ordered.append(r)
for r in row_order:
    if r not in ordered:
        ordered.append(r)
display_rails = ordered[:_MAX_RAILS]

# average groups
out_grps = sorted(groups_m.keys())
table_data = {}
for rail in display_rails:
    if rail not in matrix:
        continue
    row_avg = {}
    for grp in out_grps:
        raw_cols = groups_m[grp]
        vals_g = [matrix[rail][c] for c in raw_cols if c in matrix[rail]]
        if vals_g:
            row_avg[grp] = round(sum(vals_g) / len(vals_g), 3)
    table_data[rail] = row_avg

col_labels = [f"{g} (avg {len(groups_m[g])})" if len(groups_m[g]) > 1 else g for g in out_grps]
lines = ["| Rail | " + " | ".join(col_labels) + " |",
         "|------|" + "|".join(["------"] * len(col_labels)) + "|"]
for rail in display_rails:
    if rail not in table_data:
        continue
    cells = []
    for c in out_grps:
        v = table_data[rail].get(c, "")
        cells.append(f"{v:.2f}" if isinstance(v, float) else str(v))
    lines.append(f"| {rail} | " + " | ".join(cells) + " |")
table_md = "\n".join(lines)

result_qpm = {"success": True, "table": table_md, "rails_shown": display_rails}
t7 = time.perf_counter()
resp_qpm = json.dumps(result_qpm)
report("query_power_matrix (rails=None, cap=20)", t7 - t6, len(resp_qpm))


# ─────────────────────────────────────────────────────────────────────────────
# 5-7. query_socwatch_data — 3 batches of 4 sections
# ─────────────────────────────────────────────────────────────────────────────
_MAX_SECTION_CHARS = 1500

def _qsw(sections_req):
    md_text2 = sw_md.read_text(encoding="utf-8")
    sections_map = _extract_sections_from_md(md_text2)
    secs_lower = [s.lower() for s in sections_req]
    matched = {k: v for k, v in sections_map.items()
               if any(s in k.lower() for s in secs_lower)}
    content_parts = []
    for sec_name, sec_content in list(matched.items())[:4]:
        if len(sec_content) > _MAX_SECTION_CHARS:
            sec_content = sec_content[:_MAX_SECTION_CHARS] + "\n... [truncated]"
        content_parts.append(f"## {sec_name}\n{sec_content}")
    return {"success": True, "content": "\n\n".join(content_parts),
            "sections_shown": list(matched.keys())[:4]}

batches = [
    ["PACKAGE C-STATE (OS)", "PACKAGE C-STATE", "CORE C-STATE", "CPU P-STATE"],
    ["MEMSS P-STATE",        "DDR BANDWIDTH",   "GFX P-STATE",  "NPU D-STATE"],
    ["NPU P-STATE",          "THREAD WAKEUPS",  "PSR RESIDENCY","LTR SNOOP"],
]
resp_sw = []
for i, batch in enumerate(batches, 1):
    t_s = time.perf_counter()
    r_sw = _qsw(batch)
    t_e = time.perf_counter()
    resp_sw.append(json.dumps(r_sw))
    report(f"query_socwatch_data batch-{i} (4 sections)", t_e - t_s, len(resp_sw[-1]))


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
all_resps = [resp_kb, resp_compile, resp_parse, resp_qpm] + resp_sw
total_chars = sum(len(r) for r in all_resps)
total_tokens = total_chars // 4

print(SEP)
print(f"  {'TOTAL tool execution time':<42} {'(see above)':>20}")
print(f"  {'TOTAL chars injected into LLM context':<42} {total_chars:>14,} chars")
print(f"  {'TOTAL approx tokens in context':<42} {total_tokens:>14,} tokens")
print()

# Show per-response breakdown so largest contributors are obvious
print("  Largest responses (bottleneck candidates):")
labelled = [
    ("load_power_rail_knowledge_to_mongodb", resp_kb),
    ("compile_power_data",                  resp_compile),
    ("parse_socwatch_data",                 resp_parse),
    ("query_power_matrix",                  resp_qpm),
    ("query_socwatch_data batch-1",         resp_sw[0]),
    ("query_socwatch_data batch-2",         resp_sw[1]),
    ("query_socwatch_data batch-3",         resp_sw[2]),
]
labelled.sort(key=lambda x: len(x[1]), reverse=True)
for name, resp in labelled:
    print(f"    {name:<42} {len(resp):>7,} chars  ~{len(resp)//4:>5,} tok")
print(SEP)
