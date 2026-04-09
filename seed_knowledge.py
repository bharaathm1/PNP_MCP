"""
One-time setup script: seeds BOTH knowledge bases into the local Mongita store.

  1. Power Rail Knowledge Base     → pnp_database / power_rail_knowledge
  2. ETL DataFrame Knowledge Base  → pnp_database / etl_dataframes_knowledge

Called automatically by setup.bat after pip install.

Run manually any time to re-seed after updating either JSON:
    venv\\Scripts\\python.exe seed_knowledge.py
    venv\\Scripts\\python.exe seed_knowledge.py --force   # drop & re-seed both
"""
from __future__ import annotations

import os
import sys
import json
import argparse

# ── path bootstrap ─────────────────────────────────────────────────────────
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(THIS_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ── shared Mongita config ────────────────────────────────────────────────────
_MONGITA_PATH = os.path.join(THIS_DIR, "data", "mongita")
_MONGO_DB     = "pnp_database"

# ── JSON paths ───────────────────────────────────────────────────────────────
_POWER_JSON = os.path.join(SRC_DIR, "prompts", "knowledge", "power_rail_knowledge_base.json")
_ETL_JSON   = os.path.join(SRC_DIR, "prompts", "knowledge", "etl_dataframes_knowledge_base.json")


# ── shared collection helper ─────────────────────────────────────────────────
def _get_collection(collection_name: str):
    from mongita import MongitaClientDisk
    os.makedirs(os.path.abspath(_MONGITA_PATH), exist_ok=True)
    client = MongitaClientDisk(os.path.abspath(_MONGITA_PATH))
    return client[_MONGO_DB][collection_name]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Power Rail KB
# ─────────────────────────────────────────────────────────────────────────────
def _prepare_power_doc(entry: dict, rail_type: str) -> dict:
    doc = dict(entry)
    doc["rail_type"] = rail_type
    ips = entry.get("ips_connected", [])
    doc["ips_text"] = " | ".join(str(i) for i in ips) if isinstance(ips, list) else str(ips)
    sw = entry.get("socwatch_metrics", [])
    doc["socwatch_text"] = " | ".join(str(m) for m in sw) if isinstance(sw, list) else str(sw)
    return doc


def seed_power_rails(force: bool = False) -> None:
    print("\n[Power Rail KB]")
    print(f"  JSON  : {_POWER_JSON}")

    if not os.path.exists(_POWER_JSON):
        print("  [SKIP] JSON not found.")
        return

    with open(_POWER_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    rails_data = data.get("power_rails", {})
    soc_rails  = rails_data.get("soc_rails", [])
    plat_rails = rails_data.get("platform_rails", [])
    print(f"  Source: {len(soc_rails)} SOC + {len(plat_rails)} platform = {len(soc_rails)+len(plat_rails)} total")

    col = _get_collection("power_rail_knowledge")

    existing = col.count_documents({})
    if existing and not force:
        print(f"  [OK] Already seeded ({existing} rails). Use --force to re-seed.")
        return
    if force:
        col.delete_many({})
        print("  Cleared existing collection.")

    upserted = errors = 0
    for entry in soc_rails:
        if not entry.get("name"):
            continue
        try:
            doc = _prepare_power_doc(entry, "soc")
            existing_doc = col.find_one({"name": doc["name"]})
            if existing_doc:
                col.replace_one({"name": doc["name"]}, doc)
            else:
                col.insert_one(doc)
            upserted += 1
        except Exception as e:
            print(f"  [WARN] {entry.get('name', '?')}: {e}")
            errors += 1

    for entry in plat_rails:
        if not entry.get("name"):
            continue
        try:
            doc = _prepare_power_doc(entry, "platform")
            existing_doc = col.find_one({"name": doc["name"]})
            if existing_doc:
                col.replace_one({"name": doc["name"]}, doc)
            else:
                col.insert_one(doc)
            upserted += 1
        except Exception as e:
            print(f"  [WARN] {entry.get('name', '?')}: {e}")
            errors += 1

    total_now = col.count_documents({})
    print(f"  [OK] Seeded {upserted} rails ({total_now} total in store). Errors: {errors}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. ETL DataFrame KB
# ─────────────────────────────────────────────────────────────────────────────
def _prepare_etl_doc(entry: dict) -> dict:
    """Flatten list/dict fields into searchable text fields for keyword scoring."""
    doc = dict(entry)
    use_cases = entry.get("use_cases", "")
    doc["use_cases_text"] = (
        " | ".join(str(u) for u in use_cases) if isinstance(use_cases, list) else str(use_cases)
    )
    rc = entry.get("retrieval_code", "")
    doc["retrieval_code_text"] = (
        "\n".join(str(line) for line in rc) if isinstance(rc, list) else str(rc)
    )
    cols = entry.get("columns", {})
    doc["columns_text"] = (
        "; ".join(f"{k}: {v}" for k, v in cols.items()) if isinstance(cols, dict) else str(cols)
    )
    return doc


def seed_etl_dataframes(force: bool = False) -> None:
    print("\n[ETL DataFrame KB]")
    print(f"  JSON  : {_ETL_JSON}")

    if not os.path.exists(_ETL_JSON):
        print("  [SKIP] JSON not found.")
        return

    with open(_ETL_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("etl_dataframes", [])
    print(f"  Source: {len(entries)} dataframe entries")

    col = _get_collection("etl_dataframes_knowledge")

    existing = col.count_documents({})
    if existing and not force:
        print(f"  [OK] Already seeded ({existing} entries). Use --force to re-seed.")
        return
    if force:
        col.delete_many({})
        print("  Cleared existing collection.")

    upserted = errors = 0
    for entry in entries:
        if not entry.get("name"):
            continue
        try:
            doc = _prepare_etl_doc(entry)
            existing_doc = col.find_one({"name": doc["name"]})
            if existing_doc:
                col.replace_one({"name": doc["name"]}, doc)
            else:
                col.insert_one(doc)
            upserted += 1
        except Exception as e:
            print(f"  [WARN] {entry.get('name', '?')}: {e}")
            errors += 1

    total_now = col.count_documents({})
    print(f"  [OK] Seeded {upserted} entries ({total_now} total in store). Errors: {errors}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed all knowledge bases into the local Mongita store."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Drop existing collections and re-seed both KBs from JSON."
    )
    args = parser.parse_args()

    print(f"Mongita store: {os.path.abspath(_MONGITA_PATH)}")
    seed_power_rails(force=args.force)
    seed_etl_dataframes(force=args.force)
    print("\nDone.")
