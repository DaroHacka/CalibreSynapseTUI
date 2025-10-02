import json
import os
from datetime import datetime

class ComboUsageTracker:
    def __init__(self, path="combo_usage_cache.json"):
        self.path = path
        self.cache = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load cache: {e}")
                self.cache = {}

    def get(self, combo_key):
        return self.cache.get(combo_key)

    def store(self, combo_key, result):
        try:
            refinable = result.get("refinable_labels", {})
            books = result.get("books", {})

            # Sanitize refinable_labels: convert tuples to lists
            refinable_clean = {}
            for category, label_list in refinable.items():
                refinable_clean[category] = [
                    list(item) if isinstance(item, tuple) else item
                    for item in label_list
                ]

            # Sanitize books: remove non-serializable fields
            books_clean = {}
            for book_id, data in books.items():
                if isinstance(data, dict):
                    clean_data = {}
                    for k, v in data.items():
                        try:
                            json.dumps(v)  # test serializability
                            clean_data[k] = v
                        except TypeError:
                            clean_data[k] = str(v)
                    books_clean[book_id] = clean_data
                else:
                    books_clean[book_id] = str(data)

            self.cache[combo_key] = {
                "refinable_labels": refinable_clean,
                "books": books_clean,
                "timestamp": datetime.now().isoformat()
            }

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)

        except Exception as e:
            print(f"⚠️ Failed to save cache: {e}")