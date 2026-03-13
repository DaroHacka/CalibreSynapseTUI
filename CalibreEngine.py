import json
import os
from collections import defaultdict

class CalibreEngine:
    def __init__(self, label_map_path, vocab_path, parser_path, label_groups_path="label_groups.json"):
        self.label_map = self._load_json(label_map_path)
        self.dynamic_vocab = self._load_json(vocab_path)
        self.parser = self._load_json(parser_path)
        self.label_groups_path = label_groups_path  # Store the path for saving later
        
        # Store paths for index rebuild check
        self._label_map_path = label_map_path
        self._vocab_path = vocab_path
        
        try:
            with open(label_groups_path, "r", encoding="utf-8") as f:
                self.label_groups = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.label_groups = {}

        self.normalized_parser_labels = self._build_normalized_parser_labels()
        self.label_to_category = self._build_reverse_label_lookup()
        self._build_group_member_lookup()
        self._build_label_to_books_index()
    
    def _get_file_mtime(self, path):
        """Get file modification time, return 0 if file doesn't exist."""
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0
    
    def _should_rebuild_index(self):
        """Check if index needs rebuilding based on file timestamps."""
        index_timestamp_file = "index_timestamp.json"
        
        # Get current max mtime from our source files
        current_mtime = max(
            self._get_file_mtime(self._label_map_path),
            self._get_file_mtime(self._vocab_path)
        )
        
        # Load last build timestamp
        try:
            with open(index_timestamp_file, "r") as f:
                last_mtime = json.load(f).get("last_mtime", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            last_mtime = 0
        
        # Rebuild if current mtime is newer
        return current_mtime > last_mtime
    
    def _save_index_timestamp(self):
        """Save the current timestamp after building index."""
        index_timestamp_file = "index_timestamp.json"
        
        current_mtime = max(
            self._get_file_mtime(self._label_map_path),
            self._get_file_mtime(self._vocab_path)
        )
        
        with open(index_timestamp_file, "w") as f:
            json.dump({"last_mtime": current_mtime}, f)
    
    def _build_label_to_books_index(self):
        """Build inverted index: (field, label) -> set of book IDs. For O(1) lookups."""
        # Check if we need to rebuild (skip if no changes)
        if not self._should_rebuild_index():
            # Index already exists from previous build, skip rebuilding
            # But ensure the index exists (for first run or after reset)
            if not hasattr(self, 'label_to_books') or not self.label_to_books:
                self._do_build_index()
            return
        
        self._do_build_index()
        self._save_index_timestamp()
    
    def _do_build_index(self):
        """Actually build the inverted index."""
        self.label_to_books = {}
        for book_id, info in self.label_map.items():
            labels_by_field = info.get("labels_by_field", {})
            for field, labels in labels_by_field.items():
                for label in labels:
                    key = (field, label.strip().lower())
                    if key not in self.label_to_books:
                        self.label_to_books[key] = set()
                    self.label_to_books[key].add(book_id)

    def _build_group_member_lookup(self):
        self.group_member_lookup = {}
        for field, groups in self.label_groups.items():
            for group_name, group_data in groups.items():
                for member in group_data.get("members", []):
                    self.group_member_lookup[member.lower()] = (field, group_name)

    def _load_json(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_normalized_parser_labels(self):
        labels = set()
        for field, mapping in self.parser.items():
            for canonical, variants in mapping.items():
                labels.add(canonical.strip().lower())
                for variant in variants:
                    labels.add(variant.strip().lower())
        return labels

    def _build_reverse_label_lookup(self):
        lookup = {}
        for category, labels in self.dynamic_vocab.items():
            for label in labels:
                lookup[label.lower()] = category
        for field, mapping in self.parser.items():
            for canonical, variants in mapping.items():
                lookup[canonical.strip().lower()] = field
                for variant in variants:
                    lookup[variant.strip().lower()] = field
        return lookup

    def get_all_fields(self):
        return sorted(set(self.parser.keys()) | set(self.dynamic_vocab.keys()))

    def get_labels_for_field(self, field):
        canonical = []
        raw = []
        if field in self.parser:
            for canonical_label, variants in self.parser[field].items():
                canonical.append(canonical_label)
        raw_labels = self.dynamic_vocab.get(field, []) + self.dynamic_vocab.get(f"#{field}", [])
        raw = [label for label in raw_labels]
        return {"canonical": sorted(set(canonical)), "raw": sorted(set(raw))}

    def normalize_label(self, field, label):
        label_lower = label.strip().lower()
        if field in self.parser:
            for canonical, variants in self.parser[field].items():
                if label_lower in [v.strip().lower() for v in variants]:
                    return canonical
        return label

    def query(self, input_labels):
        # Support both old format (list of labels) and new format (dict {field: [labels]})
        # New format enables field-aware matching
        if isinstance(input_labels, dict):
            # New format: {field: [labels]}
            include_labels_by_field = {}
            for field, labels in input_labels.items():
                include_labels_by_field[field] = {label.strip().lower() for label in labels if label.strip()}
            include_labels = set()
            for labels in include_labels_by_field.values():
                include_labels.update(labels)
        else:
            # Old format: list of labels (field-agnostic - legacy behavior)
            include_labels = {label.strip().lower() for label in input_labels if label.strip()}
            include_labels_by_field = None
        
        if not include_labels:
            return {"books": {}, "refinable_labels": {}, "query_labels": [], "refinement_closed": True}

        results = {}
        for book_id, entry in self.label_map.items():
            # Build label sets per field for field-aware matching
            labels_by_field = entry.get("labels_by_field", {})
            
            if include_labels_by_field is not None:
                # Field-aware matching: check each field's labels separately
                field_match = True
                for field, required_labels in include_labels_by_field.items():
                    if not required_labels:
                        continue
                    book_field_labels = set()
                    for label in labels_by_field.get(field, []):
                        normalized = self.normalize_label(field, label)
                        book_field_labels.add(normalized.strip().lower())
                    if not required_labels.issubset(book_field_labels):
                        field_match = False
                        break
                
                if field_match:
                    normalized_by_field = {}
                    for field, field_labels in labels_by_field.items():
                        normalized_by_field[field] = [
                            self.normalize_label(field, label).strip().lower()
                            for label in field_labels
                        ]
                    # Build overall label set for refinement
                    label_set = set()
                    for field, field_labels in normalized_by_field.items():
                        label_set.update(field_labels)

                    results[book_id] = {
                        "author": entry.get("author", "Unknown"),
                        "labels": label_set,
                        "series": entry.get("series"),
                        "labels_by_field": normalized_by_field
                    }
            else:
                # Legacy field-agnostic matching
                label_set = set()
                for field, field_labels in labels_by_field.items():
                    for label in field_labels:
                        normalized = self.normalize_label(field, label)
                        label_set.add(normalized.strip().lower())

                if include_labels.issubset(label_set):
                    normalized_by_field = {}
                    for field, field_labels in labels_by_field.items():
                        normalized_by_field[field] = [
                            self.normalize_label(field, label).strip().lower()
                            for label in field_labels
                        ]

                    results[book_id] = {
                        "author": entry.get("author", "Unknown"),
                        "labels": label_set,
                        "series": entry.get("series"),
                        "labels_by_field": normalized_by_field
                    }

        remaining_labels = set()
        for data in results.values():
            remaining_labels.update(data["labels"])
        remaining_labels -= include_labels

        refinable_labels = []
        
        # Track refinements per field: {field: {label: set of series_keys}}
        field_series_tracker = defaultdict(lambda: defaultdict(set))

        for label in sorted(remaining_labels):
            for book_id, data in results.items():
                series_name = data.get("series")
                unique_key = series_name.lower() if series_name else book_id
                
                # Check if label exists in any field of this book
                labels_by_field = data.get("labels_by_field", {})
                for field, field_labels in labels_by_field.items():
                    if label in field_labels and include_labels.issubset(data["labels"]):
                        # This label exists in this specific field
                        field_series_tracker[field][label].add(unique_key)

        # Now process each field's tracker
        for field, label_tracker in field_series_tracker.items():
            for label, series_set in label_tracker.items():
                refined_count = len(series_set)
                # Only add if count is less than total results (meaning it's a valid refinement)
                # and greater than 0
                if 0 < refined_count < len(results):
                    refinable_labels.append((label, refined_count, field))

        categorized = defaultdict(list)
        for label, count, field in refinable_labels:
            raw_category = self.label_to_category.get(label, "uncategorized")
            normalized_label = label
            if raw_category in self.parser:
                for canonical, variants in self.parser[raw_category].items():
                    if label in [v.lower() for v in variants] or label == canonical.lower():
                        normalized_label = canonical
                        break
            # Only add to the field's category (not the label's inferred category)
            categorized[field].append((normalized_label, count))

        for category in categorized:
            label_counter = defaultdict(int)
            for label, count in categorized[category]:
                label_counter[label] += count
            categorized[category] = sorted(label_counter.items(), key=lambda x: x[0])

        refinement_closed = len(refinable_labels) == 0

        return {
            "books": results,
            "refinable_labels": categorized,
            "query_labels": sorted(include_labels),
            "refinement_closed": refinement_closed
        }

    def get_all_labels(self):
        all_labels = set()
        for field in self.dynamic_vocab:
            all_labels.update(self.dynamic_vocab[field])
        return list(all_labels)

    def get_groups_for_field(self, field):
        return self.label_groups.get(field, {})

    def get_group_members(self, field, group_name):
        group_data = self.label_groups.get(field, {}).get(group_name, {})
        return group_data.get("members", [])

    def is_group_member(self, label):
        return self.group_member_lookup.get(label.lower())

    def get_label_group(self, label):
        return self.group_member_lookup.get(label.lower())

    def save_label_groups(self, label_groups_path=None):
        if label_groups_path is None:
            label_groups_path = self.label_groups_path
        with open(label_groups_path, "w", encoding="utf-8") as f:
            json.dump(self.label_groups, f, indent=2)
