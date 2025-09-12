import json
from collections import defaultdict

class CalibreEngine:
    def __init__(self, label_map_path, vocab_path, parser_path):
        self.label_map = self._load_json(label_map_path)
        self.dynamic_vocab = self._load_json(vocab_path)
        self.parser = self._load_json(parser_path)

        self.normalized_parser_labels = self._build_normalized_parser_labels()
        self.label_to_category = self._build_reverse_label_lookup()

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
        include_labels = {label.strip().lower() for label in input_labels if label.strip()}
        if not include_labels:
            return {"books": {}, "refinable_labels": {}, "query_labels": [], "refinement_closed": True}

        results = {}
        for book_id, entry in self.label_map.items():
            label_set = set()
            for field, field_labels in entry.get("labels_by_field", {}).items():
                for label in field_labels:
                    normalized = self.normalize_label(field, label)
                    label_set.add(normalized.strip().lower())
            if include_labels.issubset(label_set):
                results[book_id] = {
                    "author": entry.get("author", "Unknown"),
                    "labels": label_set,
                    "series": entry.get("series")
                }

        remaining_labels = set()
        for data in results.values():
            remaining_labels.update(data["labels"])
        remaining_labels -= include_labels

        refinable_labels = []
        series_tracker = defaultdict(set)

        for label in sorted(remaining_labels):
            for book_id, data in results.items():
                series_name = data.get("series")
                unique_key = series_name.lower() if series_name else book_id
                if include_labels.union({label}).issubset(data["labels"]):
                    series_tracker[label].add(unique_key)

        for label, series_set in series_tracker.items():
            refined_count = len(series_set)
            if 0 < refined_count < len(results):
                refinable_labels.append((label, refined_count))

        categorized = defaultdict(list)
        for label, count in refinable_labels:
            raw_category = self.label_to_category.get(label, "uncategorized")
            normalized_label = label
            if raw_category in self.parser:
                for canonical, variants in self.parser[raw_category].items():
                    if label in [v.lower() for v in variants] or label == canonical.lower():
                        normalized_label = canonical
                        break
            categorized[raw_category].append((normalized_label, count))

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
