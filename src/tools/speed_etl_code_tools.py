"""
Speed ETL Code Search Tool
===========================
MCP tool that lets the agent search through speedlibs_clean.py
code entities stored in local Mongita store ( pnp_database.speed_etl_code ).

Collection seeded by:  seed_speed_etl_code.py  (run separately after setup)
Schema: name, qualified_name, class_name, entity_type, docstring,
        description, source_code, args, tags, line_start, line_end, module

NOTE: This tool returns graceful errors if the collection has not been seeded.
Seed it once by running:  venv\\Scripts\\python.exe seed_speed_etl_code.py
"""

from app import mcp
from utils.decorators import async_tool
import os

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_CURRENT_DIR      = os.path.dirname(os.path.abspath(__file__))
_MONGITA_PATH     = os.path.join(_CURRENT_DIR, "..", "..", "data", "mongita")
_MONGO_DB         = "pnp_database"
_MONGO_COLLECTION = "speed_etl_code"


def _get_collection():
    """Return Mongita collection handle (lazy import, pure-Python, no server)."""
    from mongita import MongitaClientDisk
    os.makedirs(os.path.abspath(_MONGITA_PATH), exist_ok=True)
    client = MongitaClientDisk(os.path.abspath(_MONGITA_PATH))
    return client[_MONGO_DB][_MONGO_COLLECTION]


def _format_entity(doc: dict, include_source: bool = True) -> str:
    """Format a single entity document into a human-readable block."""
    lines = []
    sep   = "─" * 56

    qname = doc.get("qualified_name", doc.get("name", "?"))
    etype = doc.get("entity_type", "unknown")
    lnum  = f"lines {doc.get('line_start','?')}–{doc.get('line_end','?')}"

    lines.append(sep)
    lines.append(f"  {qname}  [{etype}]  ({lnum})")
    lines.append(sep)

    desc = doc.get("description", "")
    if desc:
        lines.append(f"Description: {desc}")

    docstr = doc.get("docstring", "")
    if docstr and docstr != desc:
        short_doc = docstr.strip().split("\n\n")[0].strip()
        if len(short_doc) > 400:
            short_doc = short_doc[:400] + " …"
        lines.append(f"Docstring:\n{short_doc}")

    tags = doc.get("tags", [])
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")

    args = doc.get("args", [])
    sig_args = [a for a in args if a not in ("self", "cls")]
    if sig_args:
        lines.append(f"Arguments: {', '.join(sig_args)}")

    if include_source:
        src = doc.get("source_code", "")
        if src:
            # Cap source at 2 000 chars to avoid flooding the context
            if len(src) > 2000:
                src_trimmed = src[:2000] + "\n    … (truncated – see full file)"
            else:
                src_trimmed = src
            lines.append(f"Source:\n{src_trimmed}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1 : search_speed_etl_code  (main lookup tool)
# ---------------------------------------------------------------------------
@mcp.tool()
@async_tool
def search_speed_etl_code(
    query: str,
    entity_type: str = "",
    class_name:  str = "",
    top_k:       int = 5,
    include_source: bool = True,
) -> dict:
    """
    Search speedlibs_clean.py code entities by natural-language query.

    Use this tool whenever the user asks about:
      - How a specific ETL metric is extracted (CPU util, frequency, WLC …)
      - How the EtlTrace class works or any of its methods
      - Power / performance data extraction from ETL traces
      - Teams FPS, VCIP alignment, pipeline analysis logic
      - Containment breach detection, PPM settings handling
      - Trace caching strategy, pre-processing statistics
      - "Show me the code for X" requests on speedlibs_clean.py

    Args:
        query         : Natural-language description, e.g. "how is CPU
                        utilization extracted?" or "trace cache loading"
        entity_type   : Optional filter — "module_function", "class_method",
                        "class_def".  Leave blank for all types.
        class_name    : Optional filter — class scope, e.g. "EtlTrace",
                        "TeamsFPS", "VCIP_SingleETL_Enhanced", "pre_process",
                        "ContainmentBreach", "TeamsPipelineAnalysis"
        top_k         : Maximum number of results to return (default 5, max 20)
        include_source: Set False to return only descriptions without code

    Returns:
        results        : list of matched entities (qualified_name, description,
                         tags, source_code, docstring, line info)
        formatted_context : human-readable block ready for the agent to read
        total_searched : documents searched
        query_used     : the query that was executed
        tip            : guidance on follow-up
    """
    top_k = min(int(top_k), 20)

    def _strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "_id"}

    try:
        collection = _get_collection()
        total_docs = collection.count_documents({})
        if total_docs == 0:
            return {
                "error":   "Speed ETL code collection not yet seeded.",
                "tip":     "Run: venv\\Scripts\\python.exe seed_speed_etl_code.py",
                "results": [], "total_in_db": 0,
            }
    except Exception as e:
        return {
            "error":   f"Collection unavailable: {e}",
            "tip":     "Run: venv\\Scripts\\python.exe seed_speed_etl_code.py",
            "results": []
        }

    # Load all docs and filter/score in Python (Mongita has no $text/$regex)
    all_docs = [_strip(d) for d in collection.find({})]

    # Apply entity_type / class_name pre-filters
    if entity_type:
        all_docs = [d for d in all_docs if d.get("entity_type", "") == entity_type]
    if class_name:
        cn_lower = class_name.lower()
        all_docs = [d for d in all_docs if cn_lower in d.get("class_name", "").lower()]

    # Strategy 1: exact qualified_name match
    exact_results = [d for d in all_docs if d.get("qualified_name", "") == query]

    # Strategy 2: partial name match
    name_results = []
    if not exact_results:
        q_lower = query.lower()
        name_results = [d for d in all_docs
                        if query and q_lower in d.get("qualified_name", "").lower()
                        and d not in exact_results]

    # Strategy 3: keyword scoring across all text fields
    def _score(doc: dict) -> int:
        tokens = query.lower().split()
        text = " ".join([
            str(doc.get("qualified_name", "")),
            str(doc.get("description", "")),
            str(doc.get("docstring", "")),
            str(doc.get("tags", "")),
            str(doc.get("source_code", ""))[:500],
        ]).lower()
        return sum(1 for t in tokens if t in text)

    already = {d.get("qualified_name") for d in exact_results + name_results}
    text_results = []
    if query and len(exact_results) + len(name_results) < top_k:
        remaining = top_k - len(exact_results) - len(name_results)
        scored = sorted(
            [(d, _score(d)) for d in all_docs if d.get("qualified_name") not in already],
            key=lambda x: x[1], reverse=True
        )
        text_results = [d for d, s in scored[:remaining] if s > 0]

    # Merge + fallback to filter-only if nothing found
    all_results = exact_results + name_results + text_results
    if not all_results and (entity_type or class_name):
        all_results = all_docs[:top_k]

    # ---- Deduplicate preserving order --------------------------------
    seen     = set()
    deduped  = []
    for r in all_results:
        key = r.get("qualified_name", "")
        if key not in seen:
            seen.add(key)
            deduped.append(r)
        if len(deduped) >= top_k:
            break

    # ---- Build formatted_context ------------------------------------
    if deduped:
        blocks = [
            f"SpeedETL Code Search  |  query='{query}'  |  {len(deduped)} result(s)\n"
        ]
        for doc in deduped:
            blocks.append(_format_entity(doc, include_source=include_source))
        formatted_context = "\n".join(blocks)
    else:
        formatted_context = (
            f"No results found for '{query}'"
            + (f" [entity_type={entity_type}]" if entity_type else "")
            + (f" [class_name={class_name}]"  if class_name  else "")
            + ".\n\nTry a broader query such as 'cpu', 'trace', 'PPM', or 'Teams FPS'."
        )

    total = collection.count_documents({})

    return {
        "query_used":         query,
        "results_count":      len(deduped),
        "total_in_db":        total,
        "results":            deduped,
        "formatted_context":  formatted_context,
        "tip": (
            "Use the `source_code` field in each result to inspect implementation details. "
            "Use entity_type filter ('module_function'/'class_method'/'class_def') "
            "or class_name filter ('EtlTrace','TeamsFPS','VCIP_SingleETL_Enhanced', "
            "'pre_process','ContainmentBreach','TeamsPipelineAnalysis') to narrow results."
        )
    }


# ---------------------------------------------------------------------------
# Tool 2 : list_speed_etl_entities  (browse by class or type)
# ---------------------------------------------------------------------------
@mcp.tool()
@async_tool
def list_speed_etl_entities(
    class_name:  str = "",
    entity_type: str = "",
) -> dict:
    """
    List all known entities (classes / functions / methods) in speedlibs_clean.py.

    Use this tool when the user wants to:
      - See all methods of a specific class (e.g. "what can EtlTrace do?")
      - Get an overview of all module-level functions in speedlibs_clean.py
      - Browse available analysis capabilities by class

    Args:
        class_name   : Filter by class (e.g. "EtlTrace", "TeamsFPS") or blank for all
        entity_type  : "module_function" | "class_method" | "class_def" or blank for all

    Returns:
        entities     : list of {qualified_name, entity_type, description, tags}
        summary      : grouped count summary
        formatted_context : readable table of entities
    """
    try:
        collection = _get_collection()
        if collection.count_documents({}) == 0:
            return {
                "error": "Speed ETL code collection not yet seeded.",
                "tip":   "Run: venv\\Scripts\\python.exe seed_speed_etl_code.py",
                "entities": [], "entities_found": 0, "total_in_db": 0,
            }
    except Exception as e:
        return {"error": f"Collection unavailable: {e}", "entities": []}

    # Load all, filter in Python (Mongita has no $regex/$or)
    all_docs = [{k: v for k, v in d.items() if k != "_id"} for d in collection.find({})]

    if class_name:
        cn_lower = class_name.lower()
        all_docs = [d for d in all_docs if cn_lower in d.get("class_name", "").lower()]
    if entity_type:
        all_docs = [d for d in all_docs if d.get("entity_type", "") == entity_type]

    # Pick only the fields needed for the listing
    entities = sorted(
        [{"qualified_name": d.get("qualified_name", ""),
          "entity_type":    d.get("entity_type", ""),
          "class_name":     d.get("class_name", ""),
          "description":    d.get("description", ""),
          "tags":           d.get("tags", []),
          "line_start":     d.get("line_start", 0)}
         for d in all_docs],
        key=lambda x: (x["class_name"] or "~", x["line_start"])
    )

    # Group for summary
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for e in entities:
        groups[e.get("class_name") or "__module__"].append(e)

    lines = []
    for grp, items in sorted(groups.items()):
        label = grp if grp != "__module__" else "Module-level functions"
        lines.append(f"\n{'─'*50}")
        lines.append(f"  {label}  ({len(items)} entities)")
        lines.append(f"{'─'*50}")
        for item in items:
            short_desc = item.get("description", "")[:70]
            lines.append(f"  {item['qualified_name']:<45}  {item['entity_type']}")
            if short_desc:
                lines.append(f"    {short_desc}")

    formatted_context = "\n".join(lines) if lines else "No entities found."

    # Summary counts
    summary = {grp: len(items) for grp, items in groups.items()}
    total = collection.count_documents({})

    return {
        "filter_applied":    {"class_name": class_name, "entity_type": entity_type},
        "entities_found":    len(entities),
        "total_in_db":       total,
        "entities":          entities,
        "summary_by_class":  summary,
        "formatted_context": formatted_context,
    }
