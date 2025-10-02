import json
import subprocess
import re
import os

# === CONFIG ===
library_path = "/srv/dev-disk-by-uuid-2856cdb9-5991-47dc-886b-1be20f8c2993/ArkVault/Calibre Library"
vocab_path = "dynamic_vocabulary.json"
semantic_map_path = "semantic_label_map.json"
resolved_path = "resolved_labels.json"
failed_path = "failed_metadata.json"
overlap_path = "overlapping_labels.json"
affected_path = "affected_books.json"

# === STEP 1: Find globally overlapping labels ===
def find_duplicate_labels():
    with open(vocab_path, "r", encoding="utf-8") as f:
        vocab = json.load(f)

    label_fields = {}
    for field, labels in vocab.items():
        for label in labels:
            label_fields.setdefault(label, set()).add(field)

    overlapping = {label: list(fields) for label, fields in label_fields.items() if len(fields) > 1}
    with open(overlap_path, "w", encoding="utf-8") as f:
        json.dump(overlapping, f, indent=2, ensure_ascii=False)
    print(f"🔍 Found {len(overlapping)} globally overlapping labels.")

# === STEP 2: Trace affected books ===
def trace_books():
    with open(overlap_path, "r", encoding="utf-8") as f:
        overlapping = json.load(f)
    with open(semantic_map_path, "r", encoding="utf-8") as f:
        all_books = json.load(f)

    affected = {}
    for book_id, info in all_books.items():
        title = info.get("title", "Unknown Title")
        author = info.get("author", "Unknown Author")
        labels_by_field = info.get("labels_by_field", {})
        updates = {}

        for field, labels in labels_by_field.items():
            for label in labels:
                if label in overlapping:
                    updates.setdefault(field, []).append(label)

        if updates:
            affected[book_id] = {
                "title": title,
                "author": author,
                "conflicting_labels": updates
            }

    with open(affected_path, "w", encoding="utf-8") as f:
        json.dump(affected, f, indent=2, ensure_ascii=False)
    print(f"📚 Traced {len(affected)} affected books.")

# === STEP 3: Resolve conflicts ===
def resolve_conflicts():
    suffix_map = {
        "#genres": "-g", "#subgenre": "-sg", "#provenance": "-p",
        "#writing_style": "-ws", "#narrative_structure": "-ns", "#emotional_tone": "-et",
        "#character_traits": "-ct", "#book_setting": "-bs", "#reading_mood": "-rm",
        "#reading_level": "-rl", "#publication_period": "-pp", "#awards": "-a",
        "#themes": "-t", "#length": "-l", "#pacing": "-pc", "#perspective": "-pv",
        "#subject": "-s", "#movement": "-mv", "#mangagenre": "-mg",
        "authors": "", "publisher": "", "series": "", "comments": ""
    }

    def normalize_field(field):
        if field.lower().strip() == "book's setting":
            field = "Book Setting"
        f = field.lower().replace("'", "").replace("’", "").replace(" ", "_")
        return f"#" + f if not f.startswith("#") else f

    with open(affected_path, "r", encoding="utf-8") as f:
        affected = json.load(f)

    resolved = {}
    for book_id, info in affected.items():
        title = info.get("title", "Unknown Title")
        author = info.get("author", "Unknown Author")
        updates = {}
        for field, labels in info["conflicting_labels"].items():
            norm_field = normalize_field(field)
            if norm_field not in suffix_map:
                continue
            suffix = suffix_map[norm_field]
            if suffix == "":
                continue
            updated_labels = [f"{label}{suffix}" for label in labels]
            updates[norm_field] = updated_labels
        resolved[book_id] = {"title": title, "author": author, "updates": updates}

    with open(resolved_path, "w", encoding="utf-8") as f:
        json.dump(resolved, f, indent=2, ensure_ascii=False)
    print(f"🧩 Resolved {len(resolved)} books.")

# === STEP 4: Push metadata for all books ===
def push_metadata():
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            resolved = json.load(f)
    except FileNotFoundError:
        print("⚠️ resolved_labels.json not found.")
        return

    try:
        with open(failed_path, "r", encoding="utf-8") as f:
            failed = json.load(f)
    except FileNotFoundError:
        failed = {}

    processed_titles = []
    failed_titles = []

    for book_id, info in list(resolved.items()):
        title = info.get("title", "Unknown Title")
        author = info.get("author", "Unknown Author")
        updates = info.get("updates", {})

        if not updates:
            print(f"⚠️ Skipping {title} — no valid fields.")
            continue

        cmd = ["calibredb", "set_metadata", book_id, "--with-library", library_path]
        for field, labels in updates.items():
            value = ", ".join(labels)
            cmd += ["--field", f"{field}:{value}"]

        print(f"\n🚀 Pushing metadata to Calibre...\n📘 {title}\nAuthor: {author}\nBook ID: {book_id}")
        try:
            subprocess.run(cmd, check=True)
            print(f"✅ Updated: {title}")
            processed_titles.append(title)
            del resolved[book_id]
        except subprocess.CalledProcessError as e:
            print("❌ Error updating metadata:")
            print(e)
            failed[book_id] = info
            failed_titles.append(title)

    with open(resolved_path, "w", encoding="utf-8") as f:
        json.dump(resolved, f, indent=2, ensure_ascii=False)
    with open(failed_path, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=2, ensure_ascii=False)

    print("\n📚 Successfully updated:")
    for t in processed_titles:
        print(f"  • {t}")
    if failed_titles:
        print("\n⚠️ Failed to update:")
        for t in failed_titles:
            print(f"  • {t}")

# === RUN ALL STEPS ===
if __name__ == "__main__":
    find_duplicate_labels()
    trace_books()
    resolve_conflicts()
    push_metadata()
