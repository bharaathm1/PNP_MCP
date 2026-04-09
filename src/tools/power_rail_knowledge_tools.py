"""
Power Rail Knowledge Tools - MongoDB-backed SOC/Platform power rail knowledge base

This module provides:
1. load_power_rail_knowledge_to_mongodb  - Seeds / refreshes the MongoDB collection from
                                           power_rail_knowledge_base.json.
                                           Call ONCE when starting a PowerSocwatchDataCompiler
                                           session, or when the JSON is updated.
2. search_power_rail_knowledge           - Searches the collection (JSON fallback if MongoDB
                                           is unavailable) and returns structured context to
                                           ENRICH queries sent to PowerSocwatchDataCompiler.

Design notes:
- ALL pymongo imports are LAZY (inside functions) to avoid stdout pollution that
  would break the MCP JSON-RPC protocol.
- MongoDB: localhost:27017  →  pnp_database.power_rail_knowledge
  (same database as etl_dataframes_knowledge - no new DB required)
- Both soc_rails and platform_rails are stored in the same collection with a
  `rail_type` field ("soc" | "platform") for easy filtering.
- Full-text index: power_rail_text_idx  (name:10, description:5, debug_hints:4,
                                          ips_text:3, socwatch_text:2)
- Unique exact index: power_rail_name_idx (on "name" field)
- JSON fallback: reads the JSON file directly with keyword scoring when MongoDB
  is unavailable so the server never crashes.
"""

import os
import json
from typing import Annotated, Dict, Any, List, Optional

from app import mcp
from pydantic import Field
from utils.decorators import async_tool

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CURRENT_DIR    = os.path.dirname(os.path.abspath(__file__))      # src/tools/
_SRC_DIR        = os.path.dirname(_CURRENT_DIR)                   # src/
_KNOWLEDGE_JSON = os.path.join(
    _SRC_DIR, "prompts", "knowledge", "power_rail_knowledge_base.json"
)

# Mongita (pure-Python, no server) — data stored next to this repo
_MONGITA_PATH     = os.path.join(_CURRENT_DIR, "..", "..", "data", "mongita")
_MONGO_DB         = "pnp_database"
_MONGO_COLLECTION = "power_rail_knowledge"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_collection():
    """Return the Mongita collection handle (lazy import, pure-Python, no server)."""
    from mongita import MongitaClientDisk
    os.makedirs(os.path.abspath(_MONGITA_PATH), exist_ok=True)
    client = MongitaClientDisk(os.path.abspath(_MONGITA_PATH))
    return client[_MONGO_DB][_MONGO_COLLECTION]


def _ensure_indexes(collection) -> None:
    """Mongita handles its own internal indexes; no explicit creation needed."""
    pass


def _prepare_document(entry: dict, rail_type: str) -> dict:
    """Flatten list fields into searchable text strings; tag with rail_type."""
    doc = dict(entry)
    doc["rail_type"] = rail_type

    ips = entry.get("ips_connected", [])
    doc["ips_text"] = " | ".join(str(i) for i in ips) if isinstance(ips, list) else str(ips)

    sw = entry.get("socwatch_metrics", [])
    doc["socwatch_text"] = " | ".join(str(m) for m in sw) if isinstance(sw, list) else str(sw)

    return doc


def _load_all_rails() -> List[dict]:
    """Load and flatten all rails from the JSON, tagging with rail_type."""
    with open(_KNOWLEDGE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    rails = data.get("power_rails", {})
    docs = []
    for entry in rails.get("soc_rails", []):
        docs.append({"_rail_type": "soc", **entry})
    for entry in rails.get("platform_rails", []):
        docs.append({"_rail_type": "platform", **entry})
    return docs


def _keyword_score(entry: dict, query: str) -> int:
    tokens = query.lower().split()
    text = " ".join([
        str(entry.get("name", "")),
        str(entry.get("description", "")),
        str(entry.get("debug_hints", "")),
        str(entry.get("ips_connected", "")),
        str(entry.get("socwatch_metrics", "")),
    ]).lower()
    return sum(1 for t in tokens if t in text)


def _format_result(entry: dict) -> str:
    name      = entry.get("name", "unknown")
    desc      = entry.get("description", "")
    rail_type = entry.get("rail_type", entry.get("_rail_type", ""))
    ips       = entry.get("ips_connected", [])
    hints     = entry.get("debug_hints", "")
    sw        = entry.get("socwatch_metrics", [])

    lines = [
        f"### `{name}`  ({rail_type.upper()} rail)",
        f"{desc}",
        "",
    ]

    if ips:
        lines.append("**IPs Connected:**")
        if isinstance(ips, list):
            for ip in ips:
                lines.append(f"- {ip}")
        else:
            lines.append(str(ips))
        lines.append("")

    if hints:
        lines.append("**Debug / Investigation Hints:**")
        lines.append(hints)
        lines.append("")

    if sw:
        lines.append("**Relevant SocWatch Metrics:**")
        if isinstance(sw, list):
            for m in sw:
                lines.append(f"- {m}")
        else:
            lines.append(str(sw))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Tool 1 – Load / refresh power rail knowledge into MongoDB
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Load (or refresh) the SOC/Platform Power Rail knowledge base JSON into MongoDB. "
        "Call this ONCE at the start of a PowerSocwatchDataCompiler session so that "
        "search_power_rail_knowledge can retrieve rail metadata, debug hints and "
        "SocWatch metric names for query enrichment. "
        "Safe to call repeatedly (upserts by rail name). "
        "Accepts optional drop_first flag to wipe and re-seed from scratch."
    ),
    tags={"power", "rail", "knowledge", "mongodb", "setup", "socwatch"}
)
@async_tool
def load_power_rail_knowledge_to_mongodb(
    drop_first: Annotated[bool, Field(
        description="If True, drop the existing collection before re-seeding. "
                    "Useful when power_rail_knowledge_base.json has been updated.",
        default=False
    )] = False
) -> Dict[str, Any]:
    """
    Seeds the MongoDB collection `pnp_database.power_rail_knowledge` from the
    local JSON knowledge base file.

    - Upserts both soc_rails and platform_rails (tagged with rail_type).
    - Creates full-text index `power_rail_text_idx` and unique index `power_rail_name_idx`.
    - Returns a summary with counts and index info.
    """
    try:
        collection = _get_collection()

        if drop_first:
            collection.delete_many({})

        raw_docs = _load_all_rails()
        if not raw_docs:
            return {"success": False, "error": "No rails found in knowledge base JSON", "path": _KNOWLEDGE_JSON}

        upserted = skipped = 0
        errors   = []

        for raw in raw_docs:
            if not raw.get("name"):
                skipped += 1
                continue
            try:
                rail_type = raw.pop("_rail_type", "soc")
                doc = _prepare_document(raw, rail_type)
                existing = collection.find_one({"name": doc["name"]})
                if existing:
                    collection.replace_one({"name": doc["name"]}, doc)
                else:
                    collection.insert_one(doc)
                upserted += 1
            except Exception as e:
                errors.append(f"{raw.get('name', '?')}: {str(e)}")

        _ensure_indexes(collection)

        indexes    = ["mongita_local"]
        total      = collection.count_documents({})
        soc_count  = collection.count_documents({"rail_type": "soc"})
        plat_count = collection.count_documents({"rail_type": "platform"})

        return {
            "success": True,
            "upserted": upserted,
            "skipped":  skipped,
            "errors":   errors,
            "total_documents": total,
            "soc_rails": soc_count,
            "platform_rails": plat_count,
            "indexes": indexes,
            "collection": f"{_MONGO_DB}.{_MONGO_COLLECTION}",
            "source_json": _KNOWLEDGE_JSON,
            "message": (
                f"✅  Seeded {upserted} power rail entries into "
                f"`{_MONGO_DB}.{_MONGO_COLLECTION}` "
                f"({soc_count} SOC + {plat_count} platform).  "
                f"Total docs: {total}.  Indexes: {indexes}"
            )
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "hint": "Mongita storage error. Check that the data/mongita/ folder is writable."
        }


# ---------------------------------------------------------------------------
# MCP Tool 2 \u2013 Get ALL power rail knowledge (for session initialisation)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Retrieve the COMPLETE SOC and Platform Power Rail knowledge base in one call."
        " Call this ONCE at the very start of a PowerSocwatchDataCompiler session."
        " The returned `formatted_context` (all rail descriptions, connected IPs,"
        " debug hints and SocWatch metric names) should be prepended to the FIRST"
        " query sent to the agent, so the agent has full rail context for the entire"
        " conversation without needing to reload on every message."
        " Falls back to reading the JSON file directly if MongoDB is unavailable."
    ),
    tags={"power", "rail", "knowledge", "session-init", "socwatch"}
)
@async_tool
def get_all_power_rail_knowledge() -> Dict[str, Any]:
    """
    Returns all SOC and Platform power rail entries as a single formatted context block.
    Intended to be called ONCE per PowerSocwatchDataCompiler session.

    Returns:
        {
            "success": bool,
            "formatted_context": str,   \u2190 prepend to first query_adk_agent call
            "total_rails": int,
            "soc_rails": int,
            "platform_rails": int,
            "source": "mongodb" | "json_file",
            "message": str
        }
    """
    rails    = []
    source   = "unknown"

    # Try local Mongita store first
    try:
        collection = _get_collection()
        source     = "mongita"
        # Fetch all docs, strip internal _id field in Python
        soc_docs  = [{k: v for k, v in d.items() if k != "_id"}
                     for d in collection.find({"rail_type": "soc"})]
        plat_docs = [{k: v for k, v in d.items() if k != "_id"}
                     for d in collection.find({"rail_type": "platform"})]
        if not soc_docs and not plat_docs:
            raise ValueError("Collection is empty — falling back to JSON")
        rails = soc_docs + plat_docs
    except Exception:
        # JSON fallback
        source = "json_file"
        try:
            raw = _load_all_rails()
            for r in raw:
                rt = r.pop("_rail_type", "soc")
                r["rail_type"] = rt
            rails = [r for r in raw if r.get("rail_type") == "soc"] + \
                    [r for r in raw if r.get("rail_type") == "platform"]
        except Exception as e:
            return {
                "success": False,
                "formatted_context": "",
                "total_rails": 0,
                "soc_rails": 0,
                "platform_rails": 0,
                "source": source,
                "message": f"Failed to load power rail knowledge: {e}"
            }

    if not rails:
        return {
            "success": False,
            "formatted_context": "",
            "total_rails": 0,
            "soc_rails": 0,
            "platform_rails": 0,
            "source": source,
            "message": "No rails found. Run load_power_rail_knowledge_to_mongodb once to seed the local store."
        }

    soc_count  = sum(1 for r in rails if r.get("rail_type") == "soc")
    plat_count = sum(1 for r in rails if r.get("rail_type") == "platform")

    # Build one big context block: header, SOC section, Platform section
    blocks = []
    blocks.append("## SOC RAILS\n")
    for r in rails:
        if r.get("rail_type") == "soc":
            clean = {k: v for k, v in r.items()
                     if k not in ("ips_text", "socwatch_text")}
            blocks.append(_format_result(clean))
            blocks.append("")

    blocks.append("---\n\n## PLATFORM RAILS\n")
    for r in rails:
        if r.get("rail_type") == "platform":
            clean = {k: v for k, v in r.items()
                     if k not in ("ips_text", "socwatch_text")}
            blocks.append(_format_result(clean))
            blocks.append("")

    formatted_context = (
        "## POWER RAIL KNOWLEDGE BASE"
        f"  ({soc_count} SOC rails + {plat_count} Platform rails \u2014 use for all power analysis guidance)\n\n"
        + "\n".join(blocks)
        + "\n## END POWER RAIL KNOWLEDGE BASE"
    )

    return {
        "success":          True,
        "formatted_context": formatted_context,
        "total_rails":      len(rails),
        "soc_rails":        soc_count,
        "platform_rails":   plat_count,
        "source":           source,
        "message": (
            f"Loaded all {len(rails)} power rails "
            f"({soc_count} SOC + {plat_count} platform) from {source}."
        )
    }


# ---------------------------------------------------------------------------
# MCP Tool 3 \u2013 Search power rail knowledge (MongoDB + JSON fallback)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search the SOC/Platform Power Rail knowledge base to retrieve rail descriptions, "
        "connected IPs, debug/investigation hints, and relevant SocWatch metric names.\n\n"
        "PURPOSE – QUERY ENRICHMENT BEFORE CALLING PowerSocwatchDataCompiler:\n"
        "  When a user asks about power analysis (e.g. 'why is P_SOC high', "
        "'debug VCCSA regression', 'check memory power'), call this tool FIRST to "
        "retrieve the rail context.  Then REFORM the delegation query sent to "
        "PowerSocwatchDataCompiler by prepending the returned `formatted_context` so "
        "the agent knows:\n"
        "  - Which IPs are connected to the rail\n"
        "  - What SocWatch metrics to examine\n"
        "  - Debug hints specific to the rail regression\n\n"
        "TWO MODES (auto-selected):\n"
        "  1. Exact lookup  – supply `rail_names` list  → fetches exact docs by rail name\n"
        "  2. Text search   – supply only `query`       → MongoDB full-text ranked search\n\n"
        "FILTER: optionally restrict to 'soc' or 'platform' rails via `rail_type`.\n\n"
        "FALLBACK: if MongoDB is unavailable, reads the JSON file directly with keyword scoring."
    ),
    tags={"power", "rail", "knowledge", "search", "query-enrichment", "socwatch"}
)
@async_tool
def search_power_rail_knowledge(
    query: Annotated[str, Field(
        description="Natural-language description of the power question. "
                    "E.g. 'VCCSA regression', 'memory bandwidth high', 'GT power', 'P_SOC debugging'. "
                    "Used for full-text MongoDB search when rail_names is not supplied."
    )],
    rail_names: Annotated[Optional[List[str]], Field(
        description="Optional list of exact power rail names for direct lookup "
                    "(e.g. ['P_SOC', 'VCCSA', 'VCC_LP_ECORE']). "
                    "When provided, performs a direct lookup instead of text search.",
        default=None
    )] = None,
    rail_type: Annotated[Optional[str], Field(
        description="Optional filter: 'soc' to return only SOC rails, "
                    "'platform' to return only platform rails. "
                    "Leave empty to search all rails.",
        default=None
    )] = None,
    top_k: Annotated[int, Field(
        description="Maximum number of results to return (text-search mode only). Default 5.",
        default=5
    )] = 5
) -> Dict[str, Any]:
    """
    Search the Power Rail knowledge base and return structured context suitable
    for enriching PowerSocwatchDataCompiler delegation queries.

    Returns:
        {
            "success": bool,
            "results": [list of rail metadata dicts],
            "formatted_context": str,   ← prepend this to PowerSocwatchDataCompiler query
            "result_count": int,
            "search_mode": "exact_lookup"|"mongodb_text"|"json_fallback",
            "source": "mongodb"|"json_file",
            "message": str
        }
    """
    results     = []
    search_mode = "unknown"
    source      = "unknown"

    # ------------------------------------------------------------------
    # Path A: Mongita local store
    # ------------------------------------------------------------------
    try:
        collection = _get_collection()
        source     = "mongita"

        type_filter: dict = {}
        if rail_type in ("soc", "platform"):
            type_filter = {"rail_type": rail_type}

        def _strip(d: dict) -> dict:
            return {k: v for k, v in d.items() if k != "_id"}

        if rail_names:
            search_mode = "exact_lookup"
            for name in rail_names:
                filt = {"name": name, **type_filter}
                doc = collection.find_one(filt)
                if doc:
                    results.append(_strip(doc))
        else:
            # Mongita has no $text index — load all and score with keywords
            search_mode = "keyword_scoring"
            all_docs = [_strip(d) for d in collection.find(type_filter)]
            if not all_docs:
                raise ValueError("Collection empty — falling back to JSON")
            scored = [(d, _keyword_score(d, query)) for d in all_docs]
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [d for d, s in scored[:top_k] if s > 0]
            if not results:
                results = [d for d, _ in scored[:top_k]]

    # ------------------------------------------------------------------
    # Path B: JSON fallback (if Mongita store is empty or unavailable)
    # ------------------------------------------------------------------
    except Exception:
        source      = "json_file"
        search_mode = "json_fallback"
        try:
            all_rails = _load_all_rails()
            # apply rail_type filter
            if rail_type in ("soc", "platform"):
                all_rails = [r for r in all_rails if r.get("_rail_type") == rail_type]

            if rail_names:
                results = [r for r in all_rails if r.get("name") in rail_names]
            else:
                scored = [(r, _keyword_score(r, query)) for r in all_rails]
                scored.sort(key=lambda x: x[1], reverse=True)
                results = [r for r, s in scored[:top_k] if s > 0]
                if not results:
                    results = all_rails[:top_k]
        except Exception as json_exc:
            return {
                "success": False,
                "results": [],
                "formatted_context": "",
                "result_count": 0,
                "search_mode": search_mode,
                "source": source,
                "message": f"Both MongoDB and JSON fallback failed: {json_exc}"
            }

    # ------------------------------------------------------------------
    # Build formatted_context
    # ------------------------------------------------------------------
    formatted_context = ""
    if results:
        blocks = []
        for r in results:
            clean = {k: v for k, v in r.items()
                     if k not in ("score", "ips_text", "socwatch_text", "_rail_type")}
            blocks.append(_format_result(clean))

        formatted_context = (
            "## POWER RAIL CONTEXT  (retrieved from knowledge base – use for analysis guidance)\n\n"
            + "\n\n---\n\n".join(blocks)
            + "\n\n## END POWER RAIL CONTEXT"
        )

    clean_results = [
        {k: v for k, v in r.items()
         if k not in ("score", "ips_text", "socwatch_text", "_rail_type")}
        for r in results
    ]

    return {
        "success":           True,
        "results":           clean_results,
        "formatted_context": formatted_context,
        "result_count":      len(clean_results),
        "search_mode":       search_mode,
        "source":            source,
        "query":             query,
        "rail_names":        rail_names,
        "rail_type_filter":  rail_type,
        "message": (
            f"Found {len(clean_results)} rail(s) via '{search_mode}' "
            f"(source: {source}) for query '{query}'"
            if clean_results else
            f"No matching rails found for query '{query}' "
            f"(source: {source}, mode: {search_mode})"
        )
    }
