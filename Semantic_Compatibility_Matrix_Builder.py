import os
import json
import sqlite3
from collections import defaultdict

# === CONFIGURATION ===
# Replace these paths with the actual locations of your files
CALIBRE_DB_PATH = "/path/to/your/Calibre Library/metadata.db"  # Path to Calibre's metadata database
OUTPUT_LABEL_MAP = "/path/to/your/CalibreSynapseTUI/semantic_label_map.json"
DYNAMIC_VOCAB_PATH = "/path/to/your/CalibreSynapseTUI/dynamic_vocabulary.json"
VOCABULARY_PARSER_PATH = "/path/to/your/CalibreSynapseTUI/vocabulary_parser.json"
FREQUENCY_MAP_PATH = "/path/to/your/CalibreSynapseTUI/label_frequency.json"
FLAT_INDEX_PATH = "/path/to/your/CalibreSynapseTUI/flat_label_index.json"

# === ALLOWED FIELDS ===
# These are the metadata fields CalibreSynapse will use for semantic filtering.
# You must personalize this list to match the custom columns you've created in Calibre.
# Refer to the setup guide for instructions on how to define and format these fields correctly.
ALLOWED_FIELDS = {
    "Genre", "Themes", "Perspective", "Reading Mood", "Narrative Structure",
    "Emotional Tone", "Main Character Traits", "Book's Setting", "Publication Period"
}

# === CORE FIELDS ===
# These are essential fields used for grouping or display logic


# === CORE FIELDS ===
# These are essential fields used for grouping or display logic
CORE_FIELDS = {"series"}

# === INIT RESULT MAPS ===
# These dictionaries will be populated by the Semantic Matrix Builder


# === INIT RESULT MAPS ===
label_map = {}
dynamic_vocab = defaultdict(set)
label_frequency = defaultdict(int)
flat_label_index = defaultdict(list)

# === LOAD VOCABULARY PARSER ===
try:
    with open(VOCABULARY_PARSER_PATH, "r", encoding="utf-8") as f:
        vocabulary_parser = json.load(f)
    print(f"📖 Vocabulary parser loaded from: {VOCABULARY_PARSER_PATH}")
except Exception as e:
    print(f"❌ Failed to load vocabulary parser: {e}")
    vocabulary_parser = {}

# === CONNECT TO CALIBRE DATABASE ===
conn = sqlite3.connect(CALIBRE_DB_PATH)
cursor = conn.cursor()

# === HELPER: Check if table exists ===
def table_exists(cursor, table_name):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

# === DISCOVER CUSTOM COLUMNS ===
cursor.execute("SELECT id, name FROM custom_columns")
raw_columns = cursor.fetchall()

# Map field name to its column index (only if allowed and not core)
field_map = {}
for col_id, name in raw_columns:
    if name in ALLOWED_FIELDS and name not in CORE_FIELDS:
        field_map[name] = col_id

print(f"🧠 Using filtered custom fields: {list(field_map.keys())}")
print(f"🧠 Including core fields: {list(CORE_FIELDS & ALLOWED_FIELDS)}\n")

# === FETCH BOOKS ===
cursor.execute("SELECT id, title, path FROM books")
books = cursor.fetchall()
print(f"🔍 Scanning {len(books)} books...\n")

for idx, (book_id, title, path) in enumerate(books, start=1):
    book_labels = {}
    author_folder = path.split(os.sep)[0]
    series_name = None

    # === Fetch Series Name ===
    if "series" in ALLOWED_FIELDS:
        cursor.execute("""
            SELECT s.name
            FROM books_series_link l
            JOIN series s ON l.series = s.id
            WHERE l.book = ?
        """, (book_id,))
        result = cursor.fetchone()
        series_name = result[0] if result else None

    # === Fetch Custom Field Labels ===
    for field_name, col_index in field_map.items():
        link_table = f"books_custom_column_{col_index}_link"
        value_table = f"custom_column_{col_index}"

        if not table_exists(cursor, link_table) or not table_exists(cursor, value_table):
            continue

        try:
            cursor.execute(f"""
                SELECT cc.value
                FROM {link_table} l
                JOIN {value_table} cc ON l.value = cc.id
                WHERE l.book = ?
            """, (book_id,))
            values = [row[0].strip().lower() for row in cursor.fetchall() if row[0].strip()]

            for val in values:
                # Split Subject field by comma
                split_vals = [v.strip() for v in val.split(",")] if field_name == "Subject" else [val]

                for raw_val in split_vals:
                    val_clean = raw_val
                    if field_name in vocabulary_parser:
                        for canonical, variants in vocabulary_parser[field_name].items():
                            if raw_val in variants:
                                val_clean = canonical.lower()
                                break
                        if "AI" in vocabulary_parser[field_name]:
                            if val_clean in vocabulary_parser[field_name]["AI"]:
                                book_labels.setdefault("AI_flag", set()).add(field_name)

                    dynamic_vocab[field_name].add(val_clean)
                    book_labels.setdefault(field_name, set()).add(val_clean)
                    label_frequency[(field_name, val_clean)] += 1
                    flat_label_index[val_clean].append(str(book_id))

        except Exception as e:
            print(f"⚠️ Skipping field {field_name} for book {book_id}: {e}")
            continue

    if book_labels:
        label_map[str(book_id)] = {
            "title": title.strip(),
            "author": author_folder,
            "labels_by_field": {k: sorted(v) for k, v in book_labels.items()},
            "series": series_name
        }
        print(f"[{idx}/{len(books)}] ✅ {book_id} — Author: {author_folder} — {sum(len(v) for v in book_labels.values())} labels collected")

# === EXPORT DYNAMIC VOCABULARY ===
with open(DYNAMIC_VOCAB_PATH, "w", encoding="utf-8") as f:
    json.dump({k: sorted(v) for k, v in dynamic_vocab.items()}, f, indent=2, ensure_ascii=False)
print(f"\n📚 Dynamic vocabulary saved to: {DYNAMIC_VOCAB_PATH}")

# === EXPORT SEMANTIC LABEL MAP ===
with open(OUTPUT_LABEL_MAP, "w", encoding="utf-8") as f:
    json.dump(label_map, f, indent=2, ensure_ascii=False)
print(f"\n✅ Semantic label map saved to: {OUTPUT_LABEL_MAP}")

# === EXPORT LABEL FREQUENCY MAP ===
with open(FREQUENCY_MAP_PATH, "w", encoding="utf-8") as f:
    json.dump({f"{field}:{label}": count for (field, label), count in label_frequency.items()}, f, indent=2, ensure_ascii=False)
print(f"\n📈 Label frequency map saved to: {FREQUENCY_MAP_PATH}")

# === EXPORT FLAT LABEL INDEX ===
with open(FLAT_INDEX_PATH, "w", encoding="utf-8") as f:
    json.dump(flat_label_index, f, indent=2, ensure_ascii=False)
print(f"\n🔁 Flat label index saved to: {FLAT_INDEX_PATH}")
