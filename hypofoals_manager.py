import json

import placeholder_store

def clean_hypo_key(sire_name: str, dam_name: str) -> str:
    """Normalizes the cross key names accurately for consistent dictionary mappings."""
    combined = f"{sire_name} x {dam_name}".lower()
    cleaned = combined.replace("’", "").replace("'", "").replace(".", "").replace("-", "")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    return " ".join(cleaned.split()).strip()

def load_hypo_database() -> dict:
    """Load hypothetical matings from the hypothetical_matings table."""
    foals = {}
    try:
        for row in placeholder_store.load_table("hypothetical_matings"):
            key = row.get("mating_key") or ""
            if not key:
                continue
            raw = row.get("pedigree_json") or ""
            try:
                foals[key] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                foals[key] = {}
    except Exception as exc:
        print(f"⚠️ Warning loading hypothetical database ({exc}). Starting fresh.")
        return {}
    return foals

def save_hypo_database(hypo_foals_map: dict):
    """Saves matings back to the hypothetical_matings table."""
    try:
        rows = []
        for cross_key, tree in sorted(hypo_foals_map.items()):
            horse = tree.get("Horse", "") if isinstance(tree, dict) else ""
            sire_name = ""
            dam_name = ""
            if isinstance(tree, dict):
                sire_node = tree.get("Sire")
                dam_node = tree.get("Dam")
                if isinstance(sire_node, dict):
                    sire_name = sire_node.get("Horse", "")
                if isinstance(dam_node, dict):
                    dam_name = dam_node.get("Horse", "")
            rows.append({
                "mating_key": cross_key,
                "horse_name": horse,
                "sire_name": sire_name,
                "dam_name": dam_name,
                "pedigree_json": json.dumps(tree),
            })
        placeholder_store.write_table("hypothetical_matings", rows)
        print("💾 Success! Hypothetical mating saved to the hypothetical_matings table.")
    except Exception as exc:
        print(f"❌ Error saving hypothetical foal entry: {exc}")

def register_new_hypo_foal(sire_name: str, dam_name: str, combined_tree: dict):
    """High-level registration pipeline hook."""
    hypo_db = load_hypo_database()
    lookup_key = clean_hypo_key(sire_name, dam_name)
    hypo_db[lookup_key] = combined_tree
    save_hypo_database(hypo_db)
