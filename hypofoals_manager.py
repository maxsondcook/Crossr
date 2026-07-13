import os

HYPO_FILE = "hypofoals.py"

def clean_hypo_key(sire_name: str, dam_name: str) -> str:
    """Normalizes the cross key names accurately for consistent dictionary mappings."""
    combined = f"{sire_name} x {dam_name}".lower()
    cleaned = combined.replace("’", "").replace("'", "").replace(".", "").replace("-", "")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    return " ".join(cleaned.split()).strip()

def load_hypo_database() -> dict:
    """Safely retrieves the HYPO_FOALS map using dedicated script evaluations."""
    if not os.path.exists(HYPO_FILE) or os.path.getsize(HYPO_FILE) == 0:
        return {}
    try:
        namespace = {}
        with open(HYPO_FILE, "r", encoding="utf-8") as f:
            exec(f.read(), namespace)
        return namespace.get("HYPO_FOALS", {})
    except Exception as e:
        print(f"⚠️ Warning loading hypothetical database ({e}). Starting fresh.")
        return {}

def save_hypo_database(hypo_foals_map: dict):
    """Saves the map back to the flat file structure matching your main registry formats."""
    try:
        with open(HYPO_FILE, "w", encoding="utf-8") as f:
            f.write('"""\nAutomatically compiled hypothetical foal mating database\n"""\n\n')
            f.write("HYPO_FOALS = {\n")
            for cross_key, tree in sorted(hypo_foals_map.items()):
                f.write(f"    {repr(cross_key)}: {repr(tree)},\n")
            f.write("}\n")
        print("💾 Success! Hypothetical mating saved successfully to hypofoals.py.")
    except Exception as e:
        print(f"❌ Error saving hypothetical foal entry: {e}")

def register_new_hypo_foal(sire_name: str, dam_name: str, combined_tree: dict):
    """High-level registration pipeline hook."""
    hypo_db = load_hypo_database()
    lookup_key = clean_hypo_key(sire_name, dam_name)
    hypo_db[lookup_key] = combined_tree
    save_hypo_database(hypo_db)