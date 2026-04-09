"""
ETL Knowledge Tools - MongoDB-backed ETL DataFrame knowledge base search

This module provides:
1. load_etl_knowledge_to_mongodb  - Seeds / refreshes the MongoDB collection from the
                                    local JSON knowledge base file.  Call once to set up,
                                    or call again after editing the JSON to refresh.
2. search_etl_dataframe_knowledge - Searches the MongoDB collection (or falls back to
                                    direct JSON read) and returns structured context that
                                    can be used to ENRICH / REFORM queries before sending
                                    them to the etl_analyzer ADK agent.

Design notes:
- ALL pymongo imports are LAZY (inside functions) to avoid stdout pollution that
  would break the MCP JSON-RPC protocol.
- MongoDB: localhost:27017  →  pnp_database.etl_dataframes_knowledge
  (same database already used by PnP_agents - no new DB required)
- Full-text index: etl_kb_text_idx   (name:10, description:5, use_cases_text:3, notes:1)
- Unique exact index: etl_kb_name_idx (on "name" field)
- JSON fallback: if MongoDB is unavailable the tools read the JSON file directly and
  return keyword-scored results so the server never crashes.
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
_CURRENT_DIR   = os.path.dirname(os.path.abspath(__file__))       # src/tools/
_SRC_DIR        = os.path.dirname(_CURRENT_DIR)                    # src/
_KNOWLEDGE_JSON = os.path.join(
    _SRC_DIR, "prompts", "knowledge", "etl_dataframes_knowledge_base.json"
)

# Mongita (pure-Python, no server) — data stored next to this repo
_MONGITA_PATH     = os.path.join(_CURRENT_DIR, "..", "..", "data", "mongita")
_MONGO_DB         = "pnp_database"
_MONGO_COLLECTION = "etl_dataframes_knowledge"

# ---------------------------------------------------------------------------
# Internal helpers (not MCP tools - no stdout at module load time)
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


def _prepare_document(entry: dict) -> dict:
    """
    Flatten list fields into searchable text strings so MongoDB full-text
    indexing can score them.  Original fields are kept alongside.
    """
    doc = dict(entry)

    # use_cases: list[str] → joined string
    use_cases = entry.get("use_cases", "")
    if isinstance(use_cases, list):
        doc["use_cases_text"] = " | ".join(str(u) for u in use_cases)
    else:
        doc["use_cases_text"] = str(use_cases)

    # retrieval_code: list[str] | str → joined string
    rc = entry.get("retrieval_code", "")
    if isinstance(rc, list):
        doc["retrieval_code_text"] = "\n".join(str(l) for l in rc)
    else:
        doc["retrieval_code_text"] = str(rc)

    # columns: dict | str → searchable text
    cols = entry.get("columns", "")
    if isinstance(cols, dict):
        doc["columns_text"] = "; ".join(f"{k}: {v}" for k, v in cols.items())
    else:
        doc["columns_text"] = str(cols)

    return doc


def _load_json() -> List[dict]:
    """Load and return the list of etl_dataframe entries from the JSON file."""
    with open(_KNOWLEDGE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("etl_dataframes", [])


def _keyword_score(entry: dict, query: str) -> int:
    """Simple keyword scorer used in the JSON fallback path."""
    tokens = query.lower().split()
    text = " ".join([
        str(entry.get("name", "")),
        str(entry.get("description", "")),
        str(entry.get("use_cases", "")),
        str(entry.get("columns", "")),
    ]).lower()
    return sum(1 for t in tokens if t in text)


def _format_result(entry: dict) -> str:
    """Build the human-readable markdown block for a single dataframe entry (schema + use-cases only, NO code)."""
    name  = entry.get("name", "unknown")
    desc  = entry.get("description", "")
    cols  = entry.get("columns", {})
    cases = entry.get("use_cases", "")

    lines = [f"### `{name}`", f"{desc}", ""]

    # Columns
    if isinstance(cols, dict) and cols:
        lines.append("**Columns:**")
        for col_name, col_desc in cols.items():
            lines.append(f"- `{col_name}`: {col_desc}")
        lines.append("")

    # Use-cases (plain text only, no code)
    if cases:
        lines.append("**Use-cases:**")
        if isinstance(cases, list):
            for c in cases:
                lines.append(f"- {c}")
        else:
            lines.append(str(cases))
        lines.append("")

    return "\n".join(lines)


def _format_result_full(entry: dict) -> str:
    """Include retrieval_code — kept for reference / debugging only."""
    base = _format_result(entry)
    rc   = entry.get("retrieval_code", "")
    if not rc:
        return base
    code_lines = [
        "**Retrieval code (reference only):**",
        "```python",
    ]
    if isinstance(rc, list):
        code_lines.extend(rc)
    else:
        code_lines.append(str(rc))
    code_lines.append("```")
    return base + "\n" + "\n".join(code_lines)


# ---------------------------------------------------------------------------
# MCP Tool 1 – Load / refresh knowledge base into MongoDB
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Load (or refresh) the ETL DataFrame knowledge base JSON into MongoDB. "
        "Run this once after server setup, or whenever etl_dataframes_knowledge_base.json "
        "is updated.  Creates the collection + full-text search indexes automatically. "
        "Accepts optional drop_first flag to wipe and re-seed from scratch."
    ),
    tags={"etl", "knowledge", "mongodb", "setup"}
)
@async_tool
def load_etl_knowledge_to_mongodb(
    drop_first: Annotated[bool, Field(
        description="If True, drop the existing collection before re-seeding. "
                    "Useful when the JSON has been substantially changed.",
        default=False
    )] = False
) -> Dict[str, Any]:
    """
    Seeds the MongoDB collection `pnp_database.etl_dataframes_knowledge` from the
    local JSON knowledge base file.

    - Upserts documents by dataframe name (idempotent – safe to call repeatedly).
    - Creates full-text index `etl_kb_text_idx` and unique index `etl_kb_name_idx`.
    - Returns a summary with counts and index info.
    """
    try:
        # ---- lazy pymongo import ----
        collection = _get_collection()

        if drop_first:
            collection.drop()

        entries = _load_json()
        if not entries:
            return {"success": False, "error": "No entries found in knowledge base JSON", "path": _KNOWLEDGE_JSON}

        upserted = 0
        skipped  = 0
        errors   = []

        for entry in entries:
            if not entry.get("name"):
                skipped += 1
                continue
            try:
                doc = _prepare_document(entry)
                collection.update_one(
                    {"name": doc["name"]},
                    {"$set": doc},
                    upsert=True
                )
                upserted += 1
            except Exception as e:
                errors.append(f"{entry.get('name', '?')}: {str(e)}")

        # Ensure indexes exist
        _ensure_indexes(collection)

        indexes = [idx["name"] for idx in collection.list_indexes()]
        total   = collection.count_documents({})

        return {
            "success": True,
            "upserted": upserted,
            "skipped":  skipped,
            "errors":   errors,
            "total_documents": total,
            "indexes": indexes,
            "collection": f"{_MONGO_DB}.{_MONGO_COLLECTION}",
            "source_json": _KNOWLEDGE_JSON,
            "message": (
                f"✅  Seeded {upserted} ETL dataframe entries into "
                f"`{_MONGO_DB}.{_MONGO_COLLECTION}`.  "
                f"Total docs: {total}.  Indexes: {indexes}"
            )
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "hint": "MongoDB may not be running.  Start it or use search_etl_dataframe_knowledge (it has a JSON fallback)."
        }


# ---------------------------------------------------------------------------
# MCP Tool 2 – Search ETL knowledge base (MongoDB + JSON fallback)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search the ETL DataFrame knowledge base to retrieve column schemas, "
        "retrieval code snippets, and use-cases for one or more dataframes.\n\n"
        "PURPOSE - QUERY ENRICHMENT BEFORE CALLING etl_analyzer:\n"
        "  When a user asks about ETL data (e.g. 'show CPU utilization', 'PPM settings', "
        "'display frequency over time'), call this tool FIRST to get background context. "
        "Then REFORM the delegation query sent to etl_analyzer by prepending the returned "
        "`formatted_context` so the agent knows:\n"
        "  - Which DataFrame variable holds the data\n"
        "  - The exact column names it should use in generated code\n"
        "  - Ready-to-run retrieval code snippets\n"
        "  - Use-cases that match the user intent\n\n"
        "TWO MODES (auto-selected):\n"
        "  1. Exact lookup  – supply `dataframe_names` list  → fetches exact docs by name\n"
        "  2. Text search   – supply only `query`            → MongoDB full-text ranked search\n\n"
        "FALLBACK: if MongoDB is unavailable, reads the JSON file directly with keyword scoring."
    ),
    tags={"etl", "knowledge", "search", "query-enrichment", "mongodb"}
)
@async_tool
def search_etl_dataframe_knowledge(
    query: Annotated[str, Field(
        description="Natural-language description of what the user wants to analyse. "
                    "E.g. 'CPU utilization per core', 'PPM power mode', 'display cdclock frequency'. "
                    "Used for full-text MongoDB search when dataframe_names is not supplied."
    )],
    dataframe_names: Annotated[Optional[List[str]], Field(
        description="Optional list of exact dataframe variable names (e.g. ['df_cpu_util', 'df_PPM_behaviour']). "
                    "When provided, performs a direct lookup instead of text search.",
        default=None
    )] = None,
    top_k: Annotated[int, Field(
        description="Maximum number of results to return (text-search mode only). Default 5.",
        default=5
    )] = 5
) -> Dict[str, Any]:
    """
    Search the ETL DataFrame knowledge base and return structured context suitable
    for enriching ETL analyzer delegation queries.

    Returns:
        {
            "success": bool,
            "results": [list of dataframe metadata dicts],
            "formatted_context": str,   ← prepend this to etl_analyzer delegation
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

        def _strip(d: dict) -> dict:
            return {k: v for k, v in d.items() if k != "_id"}

        if dataframe_names:
            search_mode = "exact_lookup"
            for name in dataframe_names:
                doc = collection.find_one({"name": name})
                if doc:
                    results.append(_strip(doc))
        else:
            # Mongita has no $text index — load all and keyword-score
            search_mode = "keyword_scoring"
            all_docs = [_strip(d) for d in collection.find({})]
            if not all_docs:
                raise ValueError("Collection empty — falling back to JSON")
            scored = [(d, _keyword_score(d, query)) for d in all_docs]
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [d for d, s in scored[:top_k] if s > 0]
            if not results:
                results = [d for d, _ in scored[:top_k]]

    # ------------------------------------------------------------------
    # Path B: JSON fallback (Mongita store empty or unavailable)
    # ------------------------------------------------------------------
    except Exception:
        source      = "json_file"
        search_mode = "json_fallback"
        try:
            entries = _load_json()
            if dataframe_names:
                results = [e for e in entries if e.get("name") in dataframe_names]
            else:
                scored = [(e, _keyword_score(e, query)) for e in entries]
                scored.sort(key=lambda x: x[1], reverse=True)
                results = [e for e, s in scored[:top_k] if s > 0]
                if not results:
                    results = entries[:top_k]   # Return first N when no matches
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
    # Build formatted_context (schema-only — NO retrieval_code snippets)
    # This is safe to prepend directly to ADK delegation queries.
    # ------------------------------------------------------------------
    formatted_context = ""
    full_context       = ""   # includes retrieval_code, for reference/debugging
    if results:
        schema_blocks = []
        full_blocks   = []
        for r in results:
            # Strip internal MongoDB/search-score fields before formatting
            clean = {k: v for k, v in r.items()
                     if k not in ("score", "use_cases_text", "retrieval_code_text", "columns_text")}
            schema_blocks.append(_format_result(clean))
            full_blocks.append(_format_result_full(clean))

        formatted_context = (
            "## ETL DATAFRAME SCHEMA CONTEXT\n"
            "## The following DataFrames and their column schemas are relevant to the query.\n"
            "## Use these exact DataFrame variable names and column names in your analysis.\n\n"
            + "\n\n---\n\n".join(schema_blocks)
            + "\n\n## END ETL SCHEMA CONTEXT"
        )
        full_context = (
            "## ETL DATAFRAME FULL CONTEXT (includes retrieval code)\n\n"
            + "\n\n---\n\n".join(full_blocks)
            + "\n\n## END ETL FULL CONTEXT"
        )

    # Clean results for JSON serialisation (remove binary metadata keys)
    clean_results = [
        {k: v for k, v in r.items()
         if k not in ("score", "use_cases_text", "retrieval_code_text", "columns_text")}
        for r in results
    ]

    return {
        "success":           True,
        "results":           clean_results,
        "formatted_context": formatted_context,   # schema-only — safe to prepend to ADK query
        "full_context":      full_context,         # includes retrieval_code — for reference only
        "result_count":      len(clean_results),
        "search_mode":       search_mode,
        "source":            source,
        "query":             query,
        "dataframe_names":   dataframe_names,
        "message": (
            f"Found {len(clean_results)} dataframe(s) via '{search_mode}' "
            f"(source: {source}) for query '{query}'"
            if clean_results else
            f"No matching dataframes found for query '{query}' "
            f"(source: {source}, mode: {search_mode})"
        )
    }
