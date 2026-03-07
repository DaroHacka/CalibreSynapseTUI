
import os
import sys

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

#!/usr/bin/env python3
# v. 1.6.1 (patched - description popup + clock)
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import urwid
import json
import pyfiglet
import itertools
import feedparser
import logging
import re
from datetime import datetime
from CalibreEngine import CalibreEngine
from ComboUsageTracker import ComboUsageTracker

class SearchEdit(urwid.Edit):
    def __init__(self, callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._callback = callback

    def keypress(self, size, key):
        if key == 'enter':
            query = self.get_edit_text().strip()
            if query:
                self._callback(query)
            return None  # Don't pass Enter to parent
        return super().keypress(size, key)

def extract_first_link(html):
    match = re.search(r'href="([^"]+)"', html)
    if match:
        return match.group(1)
    return None

logging.basicConfig(
    filename=os.path.join(SCRIPT_DIR, 'calibre_ui.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CalibreUI:
    def __init__(self):
        try:
            self.engine = CalibreEngine(
                label_map_path=os.path.join(SCRIPT_DIR, "semantic_label_map.json"),
                vocab_path=os.path.join(SCRIPT_DIR, "dynamic_vocabulary.json"),
                parser_path=os.path.join(SCRIPT_DIR, "vocabulary_parser.json"),
                label_groups_path=os.path.join(SCRIPT_DIR, "label_groups.json")
            )
        except Exception as e:
            print(f"❌ Engine failed: {e}")
            self.engine = None

        self.in_search_mode = False
        self.cache_path = os.path.join(SCRIPT_DIR, "combo_usage_cache.json")
        self._invalidate_stale_cache()  # Check if cache is stale before loading
        self.usage_tracker = ComboUsageTracker(self.cache_path)
        self._split_cache = {}
        self._page_cache = {}
        self._refinement_cache = {}
        self._filtered_label_cache = {}

        self.selected_labels = set()  # stores (label, field) tuples
        self.expanded_categories = {}
        self.search_query = ""
        self.current_theme = "deepsea"
        self.feeds_enabled = True
        self.label_page_size = 15
        self.group_page_size = 15
        self.category_page_index = {}
        self.last_active_category = None
        self.selected_labels_order = [] # undo related

        # store last query result books mapping for series expansion and lookups
        self.last_query_series_map = {}

        # label groups
        self.expanded_groups = {}
        self.current_group_field = None
        self.group_dialog_open = False
        self.group_dialog_view = "fields"

        self.themes = {
            "deepsea": [
                ('header', 'dark blue,bold', ''),
                ('selected', 'light cyan,bold', ''),
                ('raw', 'dark gray', ''),
                ('title', 'light blue', ''),
                ('series', 'white', ''),
                ('logo', 'light magenta,bold', '')
            ],
            "sunset": [
                ('header', 'dark red,bold', ''),
                ('selected', 'yellow,bold', ''),
                ('raw', 'light gray', ''),
                ('title', 'light magenta', ''),
                ('series', 'light green', ''),
                ('logo', 'light red,bold', '')
            ]
        }

        self.selected_text = urwid.Text("📖 Welcome to CalibreSynapse — where genre meets depth.")
        self.search_edit = SearchEdit(self.perform_search, "🔎 Search Label: ")
        self.label_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.title_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.suggestion_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([
            urwid.Text("📚 Loading suggestions...")
        ]))

        logo_text = """
    ┏━╸┏━┓╻  ╻┏┓ ┏━┓┏━╸┏━┓╻ ╻┏┓╻┏━┓┏━┓┏━┓┏━╸
    ┃  ┣━┫┃  ┃┣┻┓┣┳┛┣╸ ┗━┓┗┳┛┃┗┫┣━┫┣━┛┗━┓┣╸ 
    ┗━╸╹ ╹┗━╸╹┗━┛╹┗╸┗━╸┗━┛ ╹ ╹ ╹╹ ╹╹  ┗━┛┗━╸
    """
        logo_widget_raw = urwid.Text(logo_text, wrap='clip')
        logo_widget_colored = urwid.AttrMap(logo_widget_raw, 'logo')
        self.logo_widget = urwid.Padding(
            urwid.Filler(logo_widget_colored, valign='top'),
            left=2, right=2,
            width=('relative', 60)  # or use 'fixed', e.g. width=50

        )

        self.rotating_book_widget = urwid.Text("")
        footer_text_line1 = urwid.Text("🔍 Q: Quit | C: Clear | U: Undo | G: Group Labels | Esc, P: Close Pop-up | ↑↓: Navigate | -/+: Page | Enter: Select | T: Toggle Feeds")
        footer_text_line2 = urwid.Text("🟦 Blue = Standalone Book | 🟩 Green = Series")
        footer_text_widget = urwid.Pile([footer_text_line1, footer_text_line2])

        # clock widget (digital time)
        self.clock_widget = urwid.Text("", align='right')

        undo_btn = urwid.Button("⏪ Undo Last", on_press=self.undo_last_label)
        undo_btn_map = urwid.AttrMap(undo_btn, 'header', focus_map='reversed')

        self.footer = urwid.Columns([
            ('weight', 5, footer_text_widget),
            ('pack', undo_btn_map),
            ('pack', self.clock_widget),
        ])

        self.toggle_btn = urwid.Button("🛑 Toggle Feeds", on_press=self.toggle_feeds)
        self.group_btn = urwid.Button("📁 Group Labels", on_press=self.open_group_dialog)
        toggle_row = urwid.Columns([
            urwid.AttrMap(self.toggle_btn, 'header'),
            urwid.AttrMap(self.group_btn, 'header'),
        ])

        self.theme_bar = urwid.Columns([])

        self.header = urwid.Pile([
            urwid.Columns([
                urwid.Pile([self.selected_text, self.search_edit]),
                self.theme_bar
            ]),
            toggle_row
        ])

        self.layout = urwid.Frame(
            header=self.header,
            body=self.build_body(),
            footer=self.footer
        )

        print("✅ Reached loop setup")
        self.loop = urwid.MainLoop(self.layout, palette=self.themes[self.current_theme], unhandled_input=self.handle_input, handle_mouse=True)
        self.build_theme_bar()
        self.frame_gen = self.book_frames()
        self.loop.set_alarm_in(0.1, self.animate_book)
        self.loop.set_alarm_in(0.2, lambda loop, data: self.refresh_suggestions())

        # start clock updater (every second)
        self.update_clock(None, None)

        self.build_label_list()
        self.update_titles()

    def _invalidate_stale_cache(self):
        """Check if cache is older than metadata timestamp, and delete if stale."""
        import time
        cache_path = self.cache_path
        metadata_timestamp_path = os.path.join(SCRIPT_DIR, "metadata_timestamp.json")
        
        # If no cache exists, nothing to invalidate
        if not os.path.exists(cache_path):
            return
        
        # If no metadata timestamp exists (old setup), keep cache
        if not os.path.exists(metadata_timestamp_path):
            return
        
        try:
            with open(metadata_timestamp_path, "r", encoding="utf-8") as f:
                timestamp_data = json.load(f)
                metadata_time = timestamp_data.get("last_updated", 0)
            
            cache_mtime = os.path.getmtime(cache_path)
            
            if cache_mtime < metadata_time:
                os.remove(cache_path)
                print(f"🔄 Cache invalidated - metadata is newer, cache will be rebuilt on first query")
        except Exception as e:
            print(f"⚠️ Error checking cache timestamp: {e}")

    def undo_last_label(self, button):
        if self.selected_labels_order:
            last = self.selected_labels_order.pop()
            self.selected_labels.remove(last)
            print(f"⏪ Removed last label: {last}")
            # Clear caches to prevent stale data after undo
            self._refinement_cache.clear()
            self._filtered_label_cache.clear()
            self.update_selected()
            self.update_titles()

    def strip_suffix(self, label):
        return re.sub(r"-(et|ws|bs|sg|g|p|t|s|pv|pc|rl|rm|pp|a|ct|ns|mv|mg|l)$", "", label)

    def switch_theme(self, button, theme_name):
        if theme_name in self.themes:
            self.current_theme = theme_name
            self.loop.screen.clear()
            self.loop.screen.register_palette(self.themes[theme_name])
            self.loop.draw_screen()

    def build_theme_bar(self):
        self.theme_bar = urwid.Columns([
            urwid.AttrMap(urwid.Button(name, on_press=self.switch_theme, user_data=name), 'header')
            for name in self.themes.keys()
        ])
        self.header.contents[0][0].contents[1] = (self.theme_bar, self.header.contents[0][0].contents[1][1])

    def get_split_labels(self, field, raw):
        if field in self._split_cache:
            return self._split_cache[field]
        if field == "Subject":
            split_labels = [v.strip() for label in raw for v in label.split(",") if v.strip()]
        else:
            split_labels = [label.strip() for label in raw]
        self._split_cache[field] = split_labels
        return split_labels

    def get_paginated_labels(self, field, labels):
        key = (field, tuple(labels))
        if key in self._page_cache:
            return self._page_cache[key]
        pages = list(self.paginate_labels(labels, self.label_page_size))
        self._page_cache[key] = pages
        return pages

    def get_filtered_labels(self, field, split_labels, refinement):
        # Build combo_key from (label, field) tuples - format: "label1:field1,label2:field2"
        label_field_strings = [f"{label}:{fld}" for label, fld in sorted(self.selected_labels)]
        combo_key = ",".join(label_field_strings)
        cache_key = (field, combo_key)
        if cache_key in self._filtered_label_cache:
            return self._filtered_label_cache[cache_key]

        # Pass field-aware labels to query
        result = self.usage_tracker.get(combo_key)
        if not result:
            # Convert tuple set to dict for query: {field: [labels]}
            labels_by_field_for_query = {}
            for label, fld in self.selected_labels:
                if fld not in labels_by_field_for_query:
                    labels_by_field_for_query[fld] = []
                labels_by_field_for_query[fld].append(label)
            result = self.engine.query(labels_by_field_for_query)
            self.usage_tracker.store(combo_key, result)

        books = result.get("books", {})
        label_set = set()

        for book_id in books:
            book_info = self.engine.label_map.get(book_id, {})
            labels_by_field = book_info.get("labels_by_field", {})
            for lbl in labels_by_field.get(field, []):
                label_set.add(lbl.strip().lower())

        filtered = []
        for label in sorted(split_labels):
            key = label.lower()
            # Check if this specific (label, field) tuple is selected
            if (key, field) in self.selected_labels:
                filtered.append(label)
                continue
            if self.search_query and self.search_query not in key:
                continue
            if self.selected_labels and key not in label_set:
                continue
            filtered.append(label)

        self._filtered_label_cache[cache_key] = filtered
        return filtered

    def compute_label_counts(self, field, refinement, filtered_book_ids=None):
        """
        Produce a mapping of label (lowercase) -> count.

        Strategy:
        - If refinement contains explicit counts for this field, use them as base.
        - Otherwise, fall back to scanning filtered books and counting:
            - If an item belongs to a series, count that series as 1 for the label (regardless of how many volumes).
            - If an item does NOT belong to a series, count it per book id.
        - When labels are selected (filtered_book_ids provided), count labels across ALL fields,
          not just the specific field, to match query behavior.
        
        Args:
            field: The label field to count
            refinement: Cached refinement counts from query
            filtered_book_ids: Set of book IDs to count from (only books matching current selections)
        """
        counts = {}

        # Start from refinement counts if available
        if refinement and field in refinement:
            try:
                for lbl, cnt in refinement.get(field, []):
                    counts[lbl.lower()] = int(cnt)
            except Exception:
                pass  # defensive

        # If engine or label_map missing, return whatever we have
        if not self.engine or not hasattr(self.engine, "label_map"):
            return counts

        per_label_series = {}  # key -> set of series names (lower)
        per_label_books = {}   # key -> set of book ids (standalone)

        # Only iterate over filtered books if provided, otherwise use all books
        if filtered_book_ids is not None:
            items_to_iterate = filtered_book_ids
        else:
            items_to_iterate = self.engine.label_map.keys()

        for book_id in items_to_iterate:
            info = self.engine.label_map.get(book_id)
            if not info:
                continue
            labels_by_field = info.get("labels_by_field", {})
            
            # Count labels ONLY from the specified field (not all fields)
            label_values = labels_by_field.get(field, []) if field else []
            
            if not label_values:
                continue

            # determine series name if present
            series_name = ""
            for k in ('series', 'series_name', 'series_title'):
                s = info.get(k)
                if s:
                    series_name = str(s).strip().lower()
                    break

            for raw_lbl in label_values:
                key = raw_lbl.strip().lower()
                if not key:
                    continue
                if series_name:
                    per_label_series.setdefault(key, set()).add(series_name)
                else:
                    per_label_books.setdefault(key, set()).add(book_id)

        # Merge results: refinement counts stay if present, otherwise use computed counts.
        all_keys = set(counts.keys()) | set(per_label_series.keys()) | set(per_label_books.keys())
        for key in all_keys:
            if key in counts:
                continue
            series_set = per_label_series.get(key, set())
            book_set = per_label_books.get(key, set())
            # count series as single entries (1 per unique series)
            counts[key] = len(series_set) + len(book_set)

        return counts

    def build_label_list(self, restore_focus_position=None, refinement=None):
        """Normal category/label list, unless in search mode."""
        if self.in_search_mode:
            # Don't build the normal list if in search mode
            return
        self._split_cache.clear()
        walker = self.label_listbox.body
        walker.clear()

        if not self.engine:
            walker.append(urwid.Text("❌ Engine not initialized."))
            return

        all_fields = sorted(self.engine.dynamic_vocab.keys())

        if refinement is None:
            if self.selected_labels:
                label_field_strings = [f"{label}:{fld}" for label, fld in sorted(self.selected_labels)]
                combo_key = ",".join(label_field_strings)
                refinement = self._refinement_cache.get(combo_key, {})
            else:
                refinement = {}

        # Get filtered book IDs from cached query result
        filtered_book_ids = None
        if self.selected_labels:
            label_field_strings = [f"{label}:{fld}" for label, fld in sorted(self.selected_labels)]
            combo_key = ",".join(label_field_strings)
            cached = self.usage_tracker.get(combo_key)
            if cached:
                filtered_book_ids = set(cached.get("books", {}).keys())
        
        # Keep alphabetical order - don't reorder fields
        
        for field in all_fields:
            is_expanded = self.expanded_categories.get(field, False)
            toggle = "▼" if is_expanded else "▶"
            header_btn = urwid.Button(f"{toggle} {field}")
            urwid.connect_signal(header_btn, 'click', self.toggle_category, user_arg=field)
            walker.append(urwid.AttrMap(header_btn, 'header'))

            if not is_expanded:
                continue

            self.last_active_category = field
            labels_info = self.engine.get_labels_for_field(field)
            raw = labels_info.get("raw", [])
            split_labels = self.get_split_labels(field, raw)

            groups = self.engine.get_groups_for_field(field)
            group_member_set = set()
            for group_data in groups.values():
                for member in group_data.get("members", []):
                    group_member_set.add(member.lower())

            filtered_labels = self.get_filtered_labels(field, split_labels, refinement)
            filtered_labels = [l for l in filtered_labels if l.lower() not in group_member_set]

            label_counts = self.compute_label_counts(field, refinement, filtered_book_ids)
            
            # Group pagination (15 per page)
            group_list = sorted(groups.keys())
            group_page_key = f"{field}_groups"
            group_page_index = getattr(self, f'group_page_index_{group_page_key}'.replace('-', '_'), 0)
            
            # Simple pagination for groups
            group_pages = []
            for i in range(0, len(group_list), self.group_page_size):
                group_pages.append(group_list[i:i + self.group_page_size])
            
            if not group_pages:
                group_pages = [[]]
            
            group_page_index = min(group_page_index, len(group_pages) - 1)
            setattr(self, f'group_page_index_{group_page_key}'.replace('-', '_'), group_page_index)
            current_group_page = group_pages[group_page_index]
            
            # Render groups for current page
            for group_name in current_group_page:
                group_data = groups[group_name]
                members = group_data.get("members", [])
                group_key = (field, group_name)
                is_group_expanded = group_key in self.expanded_groups

                group_toggle = "▼" if is_group_expanded else "📂"
                total_count = sum(label_counts.get(m.lower(), 0) for m in members)
                
                # Skip groups with no matching books
                if total_count == 0:
                    continue
                
                group_text = f"  {group_toggle} {group_name} ({total_count})"

                group_btn = urwid.Button(group_text)
                def make_toggle_handler(f, gname):
                    return lambda btn: self.toggle_group_expand(btn, f, gname)
                urwid.connect_signal(group_btn, 'click', make_toggle_handler(field, group_name))
                walker.append(urwid.AttrMap(group_btn, 'header', focus_map='reversed'))

                if is_group_expanded:
                    for member in members:
                        member_key = member.lower()
                        is_selected = (member_key, field) in self.selected_labels
                        count = label_counts.get(member_key, 0)
                        count_str = f" ({count})" if count > 0 else ""
                        member_text = f"    • {member}{count_str}"
                        mbtn = urwid.Button(member_text)
                        mbtn._category = field
                        urwid.connect_signal(mbtn, 'click', self.toggle_label, user_arg=(member_key, field))
                        mstyle = 'selected' if is_selected else 'raw'
                        walker.append(urwid.AttrMap(mbtn, mstyle, focus_map='reversed'))
            
            # Render groups pagination BELOW the groups
            if group_list:
                group_nav = []
                if group_page_index > 0:
                    prev_btn = urwid.Button("← Prev", on_press=self.prev_group_page, user_data=(group_page_key, field))
                    group_nav.append(urwid.AttrMap(prev_btn, 'header', focus_map='reversed'))
                
                group_nav.append(urwid.Text(f"Groups: {group_page_index + 1}/{len(group_pages)}"))
                
                if group_page_index < len(group_pages) - 1:
                    next_btn = urwid.Button("Next →", on_press=self.next_group_page, user_data=(group_page_key, field))
                    group_nav.append(urwid.AttrMap(next_btn, 'header', focus_map='reversed'))
                
                walker.append(urwid.Columns(group_nav))
            
            # Label pagination (15 per page)
            if not filtered_labels:
                walker.append(urwid.Text("⚠️ No labels to display in this category."))
                walker.append(urwid.Divider())
                continue

            pages = []
            for i in range(0, len(filtered_labels), self.label_page_size):
                pages.append(filtered_labels[i:i + self.label_page_size])

            page_index = self.category_page_index.get(field, 0)
            page_index = min(page_index, len(pages) - 1)
            self.category_page_index[field] = page_index
            current_page = pages[page_index]

            for label in current_page:
                key = label.lower()
                is_selected = (key, field) in self.selected_labels
                count = label_counts.get(key, 0)
                count_str = f" ({count})" if count > 0 else ""
                label_text = f"  • {label}{count_str}"
                btn = urwid.Button(label_text)
                btn._category = field
                urwid.connect_signal(btn, 'click', self.toggle_label, user_arg=(key, field))
                style = 'selected' if is_selected else 'raw'
                walker.append(urwid.AttrMap(btn, style, focus_map='reversed'))
            
            # Render labels pagination BELOW the labels
            label_nav = []
            if page_index > 0:
                prev_btn = urwid.Button("← Prev", on_press=self.prev_category_page, user_data=field)
                label_nav.append(urwid.AttrMap(prev_btn, 'header', focus_map='reversed'))
            
            label_nav.append(urwid.Text(f"Labels: {page_index + 1}/{len(pages)}"))
            
            if page_index < len(pages) - 1:
                next_btn = urwid.Button("Next →", on_press=self.next_category_page, user_data=field)
                label_nav.append(urwid.AttrMap(next_btn, 'header', focus_map='reversed'))
            
            walker.append(urwid.Columns(label_nav))

            walker.append(urwid.Divider())

        if restore_focus_position is not None:
            try:
                self.label_listbox.focus_position = restore_focus_position
            except IndexError:
                pass

    def toggle_category(self, button, field):
        self.expanded_categories[field] = not self.expanded_categories.get(field, False)
        if self.expanded_categories[field]:
            self.last_active_category = field
            # Save current focus position before rebuilding
            focus_position = self.label_listbox.focus_position
            self.build_label_list(restore_focus_position=focus_position)
        else:
            self.remove_category_widgets(field)

    def remove_category_widgets(self, field):
        walker = self.label_listbox.body
        new_body = []
        skip = False
        for widget in walker:
            base = widget.base_widget if isinstance(widget, urwid.AttrMap) else widget
            if isinstance(base, urwid.Button) and base.get_label().startswith(("▼", "▶")):
                label = base.get_label()
                match = re.match(r"[▶▼] (.+)", label)
                if match and match.group(1) == field:
                    skip = True
                    new_body.append(widget)
                    continue
            if skip:
                if isinstance(base, urwid.Divider):
                    skip = False
                continue
            new_body.append(widget)
        self.label_listbox.body[:] = new_body

    def get_focused_category(self):
        focus_widget = self.label_listbox.focus
        if not focus_widget:
            return self.last_active_category
        base = focus_widget.base_widget
        if hasattr(base, '_category'):
            return base._category
        if isinstance(base, urwid.Button):
            label = base.get_label()
            match = re.match(r"[▶▼] (.+)", label)
            if match:
                return match.group(1)
        return self.last_active_category

    def next_category_page(self, button=None, field=None):
        field = field or self.last_active_category
        if field:
            self.category_page_index[field] = self.category_page_index.get(field, 0) + 1
            focus_position = self.label_listbox.focus_position
            self.build_label_list(restore_focus_position=focus_position)

    def prev_category_page(self, button=None, field=None):
        field = field or self.last_active_category
        if field:
            self.category_page_index[field] = max(0, self.category_page_index.get(field, 0) - 1)
            focus_position = self.label_listbox.focus_position
            self.build_label_list(restore_focus_position=focus_position)

    def prev_group_page(self, button=None, data=None):
        if data:
            group_page_key, field = data
            key = group_page_key.replace('-', '_')
            current = getattr(self, f'group_page_index_{key}', 0)
            setattr(self, f'group_page_index_{key}', max(0, current - 1))
            focus_position = self.label_listbox.focus_position
            self.build_label_list(restore_focus_position=focus_position)

    def next_group_page(self, button=None, data=None):
        if data:
            group_page_key, field = data
            key = group_page_key.replace('-', '_')
            current = getattr(self, f'group_page_index_{key}', 0)
            setattr(self, f'group_page_index_{key}', current + 1)
            focus_position = self.label_listbox.focus_position
            self.build_label_list(restore_focus_position=focus_position)

    def toggle_label(self, button, label_or_tuple):
        # Handle tuple from user_arg - urwid passes tuple as single arg
        if isinstance(label_or_tuple, tuple):
            label, field = label_or_tuple
        else:
            # Legacy format or just label name
            label = label_or_tuple
            field = None
        label_field_tuple = (label, field)
        if label_field_tuple in self.selected_labels:
            self.selected_labels.remove(label_field_tuple)
            if label_field_tuple in self.selected_labels_order:
                self.selected_labels_order.remove(label_field_tuple)
        else:
            self.selected_labels.add(label_field_tuple)
            if label_field_tuple not in self.selected_labels_order:
                self.selected_labels_order.append(label_field_tuple)
        
        # Save focus position to restore after rebuilding UI
        try:
            focus_position = self.label_listbox.focus_position
        except (IndexError, AttributeError):
            focus_position = None
        
        self.update_selected()
        self.update_titles(restore_focus_position=focus_position)

    def select_from_search(self, button, label_or_tuple):
        """When user selects a label from search, add it and restore normal UI."""
        # Handle tuple from user_arg - urwid passes tuple as single arg
        if isinstance(label_or_tuple, tuple):
            label, field = label_or_tuple
        else:
            label = label_or_tuple
            field = None
        self.search_query = ""
        self.search_edit.set_edit_text("")
        label_field_tuple = (label, field)
        self.selected_labels.add(label_field_tuple)
        if label_field_tuple not in self.selected_labels_order:
            self.selected_labels_order.append(label_field_tuple)
        self.in_search_mode = False  # <--- Restore normal list
        self.update_selected()
        self.update_titles()
        self.build_label_list()

    def perform_search(self, query):
        """Show search results for labels matching query, from all categories."""
        self.in_search_mode = True
        self.search_query = query
        if not self.engine:
            self.label_listbox.body[:] = [urwid.Text("❌ Engine not initialized.")]
            return

        all_fields = sorted(self.engine.dynamic_vocab.keys())
        all_label_results = []
        for field in all_fields:
            raw_labels = self.engine.get_labels_for_field(field).get("raw", [])
            for label in raw_labels:
                if query.lower() in label.lower():
                    all_label_results.append((label, field))

        if all_label_results:
            self.label_listbox.body[:] = [urwid.Text(f"🔍 Results for '{query}':")]
            for label, field in all_label_results:
                label_text = f"• {label} ({field})"
                btn = urwid.Button(label_text)
                urwid.connect_signal(btn, 'click', self.select_from_search, user_arg=(label.lower(), field))
                self.label_listbox.body.append(urwid.AttrMap(btn, 'raw', focus_map='reversed'))
        else:
            self.label_listbox.body[:] = [urwid.Text(f"🔍 No results for '{query}'.")]

    def paginate_labels(self, labels, page_size):
        for i in range(0, len(labels), page_size):
            yield labels[i:i + page_size]

    def paginate(self, entries, page_size):
        for i in range(0, len(entries), page_size):
            yield entries[i:i + page_size]

    def update_titles(self, restore_focus_position=None):
        walker = self.title_listbox.body
        walker.clear()

        # reset series map for this query
        self.last_query_series_map = {}

        if not self.selected_labels or not self.engine:
            walker.append(urwid.Text("📘 Select a label to view matching titles."))
            self.build_label_list(restore_focus_position=restore_focus_position)
            return

        # Build combo_key with field info: "label1:field1,label2:field2"
        label_field_strings = [f"{label}:{fld}" for label, fld in sorted(self.selected_labels)]
        combo_key = ",".join(label_field_strings)
        cached = self.usage_tracker.get(combo_key)

        if cached:
            print(f"🧠 Cache hit for {combo_key}")
            result = cached
        else:
            print(f"🔄 Live query for {combo_key}")
            # Convert tuple set to dict for query: {field: [labels]}
            labels_by_field_for_query = {}
            for label, fld in self.selected_labels:
                if fld not in labels_by_field_for_query:
                    labels_by_field_for_query[fld] = []
                labels_by_field_for_query[fld].append(label)
            result = self.engine.query(labels_by_field_for_query)
            self.usage_tracker.store(combo_key, result)

        refinement = result.get("refinable_labels", {})
        self._refinement_cache[combo_key] = refinement
        self.build_label_list(refinement=refinement, restore_focus_position=restore_focus_position)

        books = result.get("books", {})
        seen_series = set()

        # Build mapping series -> volumes (only from current result/books)
        for book_id, data in books.items():
            if not data:
                continue
            title = self.engine.label_map.get(book_id, {}).get("title", "").strip()
            raw_series = (data.get("series") or "").strip()
            norm_series = raw_series.lower() if raw_series else None
            author = data.get("author", "Unknown")

            volume_entry = {
                "book_id": book_id,
                "title": title or book_id.split(":")[-1].strip(),
                "author": author,
                "raw_title": title,
                "data": data
            }

            # attach description/synopsis if available in label_map (store raw html but will unwrap later)
            info = self.engine.label_map.get(book_id, {}) if self.engine else {}
            desc = info.get("description") or info.get("summary") or info.get("comments") or info.get("annotation") or ""
            volume_entry["description"] = desc

            if norm_series:
                self.last_query_series_map.setdefault(norm_series, []).append(volume_entry)
            else:
                # for standalone books, keep them keyed by book_id so open_volume_info can find them if clicked
                self.last_query_series_map.setdefault(book_id, []).append(volume_entry)

        # Now display entries: one row per series (clickable) and per standalone book
        for book_id, data in books.items():
            if not data:
                continue

            title = self.engine.label_map.get(book_id, {}).get("title", "").strip()
            raw_series = (data.get("series") or "").strip()
            norm_series = raw_series.lower() if raw_series else None
            author = data.get("author", "Unknown")

            if norm_series:
                # Create a single clickable row for the series (one line only)
                if norm_series in seen_series:
                    continue
                seen_series.add(norm_series)
                display_title = title or (self.last_query_series_map.get(norm_series, [{}])[0].get("title", "") or book_id)
                btn_label = f"📗 {display_title} (Series: {raw_series}) — Author: {author}"
                btn = urwid.Button(btn_label)
                urwid.connect_signal(btn, 'click', self.open_series_popup, user_arg=norm_series)
                walker.append(urwid.AttrMap(btn, 'title', focus_map='reversed'))
            else:
                # standalone book -> clickable to show description/info
                display_title = title or book_id.split(":")[-1].strip()
                btn_label = f"📘 {display_title} — Author: {author}"
                btn = urwid.Button(btn_label)
                # create the volume dict for this standalone and pass to open_volume_info
                volume = self.last_query_series_map.get(book_id, [{}])[0]
                urwid.connect_signal(btn, 'click', self.open_volume_info, user_arg=volume)
                walker.append(urwid.AttrMap(btn, 'title', focus_map='reversed'))

    def open_series_popup(self, button, series_key):
        """
        Show an overlay listing volumes in the series (from the last query results).
        Each volume is shown with title and author. A Close button dismisses the overlay.
        """
        volumes = self.last_query_series_map.get(series_key, [])

        body = []
        if not volumes:
            body.append(urwid.Text("No volumes found for this series in the current result set."))
        else:
            # Show series pretty title (attempt to restore capitalization)
            pretty_series = volumes[0].get("data", {}).get("series") or series_key
            body.append(urwid.Text(("header", f"Series: {pretty_series} — Volumes ({len(volumes)} shown)")))
            body.append(urwid.Divider())
            for v in sorted(volumes, key=lambda x: (x.get("title") or "").lower()):
                t = v.get("title") or v.get("book_id")
                a = v.get("author", "Unknown")
                vol_btn = urwid.Button(f"• {t} — {a}")
                urwid.connect_signal(vol_btn, 'click', self.open_volume_info, user_arg=v)
                body.append(urwid.AttrMap(vol_btn, 'raw', focus_map='reversed'))
            body.append(urwid.Divider())

        close_btn = urwid.Button("Close")
        urwid.connect_signal(close_btn, 'click', lambda btn: self._close_overlay())
        body.append(urwid.AttrMap(close_btn, 'header', focus_map='reversed'))

        pile = urwid.Pile(body)
        filler = urwid.Filler(pile, valign='top')
        box = urwid.LineBox(filler, title="Series Volumes")
        overlay = urwid.Overlay(box, self.layout,
                                align='center', width=('relative', 70),
                                valign='middle', height=('relative', 70))
        self.loop.widget = overlay

        # allow ESC to close
        def dismiss(key):
            if key in ('esc', 'p'):
                self._close_overlay()

        self.loop.unhandled_input = dismiss

    def open_volume_info(self, button, volume):
        """
        Show a popup with detailed info about the selected volume including description (cleaned from HTML).
        volume: dict with keys book_id, title, author, description, data
        """
        title = volume.get("title") or volume.get("book_id")
        author = volume.get("author", "Unknown")
        book_id = volume.get("book_id")
        # Attempt to collect more metadata from engine.label_map if available
        info = self.engine.label_map.get(book_id, {}) if self.engine else {}
        series = info.get("series") or info.get("series_name") or ""
        # Prefer description passed in volume; fallback to label_map fields
        desc = volume.get("description") or info.get("description") or info.get("summary") or info.get("comments") or ""
        cleaned_desc = re.sub(r'<.*?>', '', desc).strip()
        if not cleaned_desc:
            cleaned_desc = "No description available."

        meta_lines = [
            ("title", f"Title: {title}"),
            ("series", f"Series: {series}" if series else "Series: —"),
            ("raw", f"Author: {author}"),
            ("raw", f"Book ID: {book_id}"),
            ("raw", ""),
            ("raw", "Description:"),
        ]

        body = [urwid.Text(t[1]) for t in meta_lines]
        body.append(urwid.Divider())
        body.append(urwid.Text(cleaned_desc, wrap='any'))
        body.append(urwid.Divider())

        close_btn = urwid.Button("Close")
        urwid.connect_signal(close_btn, 'click', lambda btn: self._close_overlay())
        body.append(urwid.AttrMap(close_btn, 'header', focus_map='reversed'))

        pile = urwid.Pile(body)
        box = urwid.LineBox(urwid.Filler(pile, valign='top'), title="Volume Info")
        overlay = urwid.Overlay(box, self.layout,
                                align='center', width=('relative', 70),
                                valign='middle', height=('relative', 70))
        self.loop.widget = overlay

        def dismiss(key):
            if key in ('esc', 'p'):
                self._close_overlay()

        self.loop.unhandled_input = dismiss

    def _close_overlay(self):
        self.loop.widget = self.layout
        self.loop.unhandled_input = self.handle_input  # restore normal handler

    def build_body(self):
        left_column = urwid.LineBox(self.label_listbox, title="📂 Labels")

        main_right = urwid.Columns([
            ('weight', 2, urwid.Pile([
                ('weight', 3, urwid.LineBox(self.title_listbox, title="📚 Titles")),
                ('pack', urwid.Padding(self.logo_widget, left=2, right=2)),
                ('pack', urwid.BoxAdapter(
                    urwid.Filler(
                        urwid.Columns([
                            ('weight', 1, urwid.Text("")),
                            ('pack', self.rotating_book_widget),
                            ('weight', 1, urwid.Text(""))
                        ]),
                        valign='top'
                    ),
                    height=1
                ))
            ])),

            ('weight', 1, urwid.LineBox(self.suggestion_listbox, title="📰 Book Feeds"))
        ])

        return urwid.Columns([
            ('weight', 1, urwid.LineBox(self.label_listbox, title="📂 Labels")),
            ('weight', 2, main_right)
        ])

    def book_frames(self):
        frames = ["📘", "📗", "📙", "📕", "📓", "📔", "📒", "📚"]
        return itertools.cycle(frames)

    def animate_book(self, loop, user_data):
        self.rotating_book_widget.set_text(next(self.frame_gen))
        loop.set_alarm_in(0.1, self.animate_book)

    def update_clock(self, loop, user_data):
        """
        Update the digital clock every second.
        """
        now = datetime.now()
        self.clock_widget.set_text(now.strftime("%Y-%m-%d %H:%M:%S"))
        # re-schedule
        try:
            self.loop.set_alarm_in(1, self.update_clock)
        except Exception:
            # in case loop is not yet available or shutting down
            pass

    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key in ('c', 'C'):
            self.selected_labels.clear()
            self.selected_labels_order.clear()
            self.search_query = ""
            self.search_edit.set_edit_text("")
            self._refinement_cache.clear()
            self._filtered_label_cache.clear()
            self._page_cache.clear()
            self.update_selected()
            self.update_titles()
            self.build_label_list()
        elif key in ('t', 'T'):
            self.toggle_feeds(None)
        elif key in ('g', 'G'):
            self.open_group_dialog()
        elif key in ('u', 'U'):
            self.undo_last_label(None)
        elif key == 'enter':
            if self.in_search_mode:
                return
            focus_widget = self.label_listbox.focus
            focus_position = self.label_listbox.focus_position
            base = focus_widget.base_widget
            if isinstance(base, urwid.Button):
                label = base.get_label()
                match = re.match(r"[▶▼] (.+)", label)
                if match:
                    field = match.group(1)
                    self.toggle_category(None, field)
                    self.build_label_list(restore_focus_position=focus_position)
                    return
            if hasattr(base, '_category'):
                label_text = base.get_label()
                label_clean = label_text.strip().lstrip("•").split("(", 1)[0].strip().lower()
                field = base._category
                self.toggle_label(None, label_clean, field)
                # Don't rebuild label list - toggle_label already updates the UI
        elif key in ('-', '+'):
            field = self.get_focused_category()
            if field:
                focus_position = self.label_listbox.focus_position
                # Simpler approach: determine which pagination to use based on field
                # Check if there's a current page index for this field
                current_page = self.category_page_index.get(field, 0)
                
                if key == '+':
                    self.next_category_page(field=field)
                else:
                    self.prev_category_page(field=field)
                
                # Rebuild and restore focus
                self.build_label_list(restore_focus_position=focus_position)

    def update_selected(self):
        if self.selected_labels:
            # Extract just the label names (not the field) for display
            label_names = [label for label, field in sorted(self.selected_labels)]
            self.selected_text.set_text("🎯 Selected Labels: " + ", ".join(label_names))
        else:
            self.selected_text.set_text("📖 Welcome to CalibreSynapse — where genre meets depth.")

    def toggle_feeds(self, button):
        self.feeds_enabled = not self.feeds_enabled
        self.refresh_suggestions()

    def open_group_dialog(self, button=None):
        if not self.engine:
            return

        self.group_dialog_open = True
        self.group_dialog_view = "fields"  # "fields" or "labels"
        self.current_group_field = None
        self._build_group_dialog()

    def _build_group_dialog(self):
        if not self.engine:
            return

        if self.group_dialog_view == "fields":
            self._build_group_fields_view()
        else:
            self._build_group_labels_view()

    def _build_group_fields_view(self):
        """Build the fields selection view with simple scrollable list."""
        all_fields = sorted(self.engine.dynamic_vocab.keys())
        
        dialog_content = []
        
        header = urwid.Text("📁 Select a Field for Grouping", wrap='clip')
        dialog_content.append(header)
        dialog_content.append(urwid.Divider())
        
        # Simple scrollable list of fields
        for field in all_fields:
            btn = urwid.Button(f"  {field}  ")
            urwid.connect_signal(btn, 'click', self._select_group_field, user_arg=field)
            dialog_content.append(urwid.AttrMap(btn, 'header', focus_map='reversed'))
        
        if not all_fields:
            dialog_content.append(urwid.Text("⚠️ No fields available."))
        
        dialog_content.append(urwid.Divider())
        
        close_btn = urwid.Button("✖ Close")
        urwid.connect_signal(close_btn, 'click', self._close_group_dialog)
        
        dialog_content.append(urwid.Padding(close_btn, align='right', left=2, right=2))
        
        pile = urwid.Pile(dialog_content)
        filler = urwid.Filler(pile, valign='top')
        
        group_box = urwid.LineBox(filler, title="Group Labels")
        
        self.group_overlay = urwid.Overlay(
            group_box,
            self.layout,
            align='center',
            width=('relative', 70),
            valign='middle',
            height=('relative', 70)
        )
        self.loop.widget = self.group_overlay
        self.loop.draw_screen()

    def _build_group_labels_view(self):
        """Build the labels view for creating groups."""
        field = self.current_group_field
        if not field:
            return
            
        groups = self.engine.get_groups_for_field(field)
        labels_info = self.engine.get_labels_for_field(field)
        all_labels = sorted(labels_info.get("raw", []))

        group_member_set = set()
        for group_data in groups.values():
            for member in group_data.get("members", []):
                group_member_set.add(member.lower())

        available_labels = [l for l in all_labels if l.lower() not in group_member_set]

        # Build header section (fixed)
        header_section = []
        header = urwid.Text(f"📁 Group Labels - {field}", wrap='clip')
        header_section.append(header)
        
        back_btn = urwid.Button("← Back to Fields")
        urwid.connect_signal(back_btn, 'click', self._back_to_fields)
        header_section.append(back_btn)
        
        group_name_edit = urwid.Edit("Group name: ", "")
        header_section.append(group_name_edit)
        
        header_pile = urwid.Pile(header_section)

        # Build label list section (scrollable)
        label_section = []
        cb_widgets = {}
        for label in available_labels:
            cb = urwid.CheckBox(label, state=False)
            cb_widgets[label] = cb
            label_section.append(cb)
        
        label_listbox = urwid.ListBox(urwid.SimpleFocusListWalker(label_section))
        label_listbox_wrap = urwid.BoxAdapter(label_listbox, height=25)

        # Add scroll indicators (ASCII arrows)
        scroll_indicator_top = urwid.Text("  ▲ Scroll Up/Down ▲", align='center')
        scroll_indicator_bottom = urwid.Text("  ▼ Scroll Up/Down ▼", align='center')

        # Build footer section (fixed)
        def create_group(btn):
            group_name = group_name_edit.get_edit_text().strip()
            if not group_name:
                return

            selected_members = [label for label, cb in cb_widgets.items() if cb.get_state()]
            if not selected_members:
                return

            if field not in self.engine.label_groups:
                self.engine.label_groups[field] = {}

            self.engine.label_groups[field][group_name] = {
                "members": selected_members,
                "description": ""
            }

            self.engine.save_label_groups()
            self.expanded_groups = {}
            self.build_label_list()
            self._back_to_fields(None)

        create_btn = urwid.Button("✓ Create Group")
        urwid.connect_signal(create_btn, 'click', create_group)
        
        def close_dialog(btn):
            self.group_dialog_open = False
            self.group_overlay = None
            self.loop.widget = self.layout

        close_btn = urwid.Button("✖ Close")
        urwid.connect_signal(close_btn, 'click', close_dialog)

        # Show existing groups in a separate column (right side)
        existing_groups = list(groups.keys())
        groups_section = []
        
        self.selected_group_in_dialog = getattr(self, 'selected_group_in_dialog', None)
        
        if existing_groups:
            groups_section.append(urwid.Text("📂 Groups (click to select):"))
            for gname in existing_groups:
                members = groups[gname].get("members", [])
                gtext = f"  📂 {gname} ({len(members)})"
                
                # Create a row with group name and buttons (only for selected)
                if self.selected_group_in_dialog == gname:
                    # Selected group - show with action buttons
                    edit_btn = urwid.Button("Edit")
                    rename_btn = urwid.Button("Rename")
                    delete_btn = urwid.Button("🗑️")
                    
                    def make_edit_handler(fld, gnm):
                        return lambda btn: self._show_edit_group(fld, gnm)
                    def make_rename_handler(fld, gnm):
                        return lambda btn: self._show_rename_dialog(fld, gnm)
                    def make_delete_handler(fld, gnm):
                        return lambda btn: self._show_delete_confirmation(fld, gnm)
                    
                    urwid.connect_signal(edit_btn, 'click', make_edit_handler(field, gname))
                    urwid.connect_signal(rename_btn, 'click', make_rename_handler(field, gname))
                    urwid.connect_signal(delete_btn, 'click', make_delete_handler(field, gname))
                    
                    group_row = urwid.Columns([
                        ('weight', 1, urwid.Text(gtext)),
                        ('pack', urwid.AttrMap(edit_btn, 'header', focus_map='reversed')),
                        ('pack', urwid.AttrMap(rename_btn, 'header', focus_map='reversed')),
                        ('pack', urwid.AttrMap(delete_btn, 'header', focus_map='reversed')),
                    ])
                    groups_section.append(urwid.AttrMap(group_row, 'selected', focus_map='reversed'))
                else:
                    # Not selected - just show group name (clickable)
                    group_btn = urwid.Button(gtext)
                    
                    def make_select_handler(fld, gnm):
                        return lambda btn: self._select_group_in_dialog(fld, gnm)
                    urwid.connect_signal(group_btn, 'click', make_select_handler(field, gname))
                    
                    groups_section.append(urwid.AttrMap(group_btn, 'header', focus_map='reversed'))
            
            # Add placeholder if no group selected
            if not self.selected_group_in_dialog:
                groups_section.append(urwid.Text("  ← Select a group to edit"))
        else:
            groups_section.append(urwid.Text("  (no groups yet)"))
        
        groups_listbox = urwid.ListBox(urwid.SimpleFocusListWalker(groups_section))
        groups_listbox_wrap = urwid.BoxAdapter(groups_listbox, height=25)
        
        # Footer with Create and Close buttons
        footer_section = []
        footer_section.append(urwid.Divider())
        
        create_close_buttons = urwid.Columns([
            urwid.AttrMap(create_btn, 'header', focus_map='reversed'),
            urwid.AttrMap(close_btn, 'header', focus_map='reversed'),
        ])
        footer_section.append(create_close_buttons)
        
        # Build left column (labels for creating new groups)
        left_column = urwid.Pile([
            ('pack', header_pile),
            ('pack', scroll_indicator_top),
            label_listbox_wrap,
            ('pack', scroll_indicator_bottom),
        ])
        
        # Build right column (existing groups)
        right_column = urwid.Pile([
            ('pack', urwid.Text(" ")),
            ('pack', groups_listbox_wrap),
        ])
        
        # Combine both columns
        main_content = urwid.Columns([
            ('weight', 1, left_column),
            ('weight', 1, urwid.LineBox(right_column, title="📂 Groups")),
        ])
        
        footer_pile = urwid.Pile(footer_section)

        # Combine all sections
        dialog_content = urwid.Pile([
            main_content,
            footer_pile,
        ])
        
        filler = urwid.Filler(dialog_content, valign='top')
        
        group_box = urwid.LineBox(filler, title="Group Labels")

        self.group_overlay = urwid.Overlay(
            group_box,
            self.layout,
            align='center',
            width=('relative', 95),
            valign='middle',
            height=('relative', 70)
        )
        self.loop.widget = self.group_overlay
        
        def handle_group_dialog_input(key):
            if not isinstance(key, str):
                return None
            if key == 'esc':
                self._close_group_dialog(None)
            return None
        
        self.loop.unhandled_input = handle_group_dialog_input
        self.loop.draw_screen()

    def _select_group_field(self, button, field):
        """Select a field and switch to labels view."""
        self.current_group_field = field
        self.group_dialog_view = "labels"
        self._build_group_dialog()

    def _back_to_fields(self, btn):
        """Go back to fields selection view."""
        self.group_dialog_view = "fields"
        self.current_group_field = None
        self._build_group_dialog()

    def _close_group_dialog(self, btn):
        """Close the group dialog."""
        self.group_dialog_open = False
        self.group_overlay = None
        self.loop.widget = self.layout
        self.loop.unhandled_input = self.handle_input
        self.selected_group_in_dialog = None

    def _select_group_in_dialog(self, field, group_name):
        """Select a group in the dialog and refresh to show highlighting."""
        self.selected_group_in_dialog = group_name
        self._build_group_labels_view()

    def _show_delete_confirmation(self, field, group_name):
        """Show confirmation dialog before deleting a group."""
        dialog_content = []
        
        header = urwid.Text(f"🗑️ Delete Group: {group_name}?", wrap='clip')
        dialog_content.append(header)
        dialog_content.append(urwid.Divider())
        
        warning = urwid.Text("⚠️ Are you sure? This will NOT delete the labels inside the group, they will just become visible again in the label list.", wrap='space')
        dialog_content.append(warning)
        dialog_content.append(urwid.Divider())
        
        def confirm_delete(btn):
            # Remove the group (not the labels inside)
            if field in self.engine.label_groups:
                if group_name in self.engine.label_groups[field]:
                    del self.engine.label_groups[field][group_name]
                    self.engine.save_label_groups()
                    self.expanded_groups = {}
                    self.build_label_list()
            # Refresh the dialog
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        def cancel_delete(btn):
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        yes_btn = urwid.Button("✓ Yes, Delete")
        no_btn = urwid.Button("✖ Cancel")
        
        urwid.connect_signal(yes_btn, 'click', confirm_delete)
        urwid.connect_signal(no_btn, 'click', cancel_delete)
        
        action_buttons = urwid.Columns([
            urwid.AttrMap(yes_btn, 'header', focus_map='reversed'),
            urwid.AttrMap(no_btn, 'header', focus_map='reversed'),
        ])
        dialog_content.append(action_buttons)
        
        pile = urwid.Pile(dialog_content)
        filler = urwid.Filler(pile, valign='top')
        
        confirm_box = urwid.LineBox(filler, title="Confirm Delete")
        
        self.group_overlay = urwid.Overlay(
            confirm_box,
            self.layout,
            align='center',
            width=('relative', 50),
            valign='middle',
            height=('relative', 30)
        )
        self.loop.widget = self.group_overlay
        self.loop.draw_screen()

    def _show_edit_group(self, field, group_name):
        """Show dialog to edit a group's members (add/remove labels)."""
        group_data = self.engine.label_groups.get(field, {}).get(group_name, {})
        current_members = group_data.get("members", [])
        
        labels_info = self.engine.get_labels_for_field(field)
        all_labels = sorted(labels_info.get("raw", []))
        
        all_group_members = set()
        for gname, gdata in self.engine.label_groups.get(field, {}).items():
            for member in gdata.get("members", []):
                all_group_members.add(member.lower())
        
        available_labels = [l for l in all_labels if l.lower() not in all_group_members]
        
        header = urwid.Text(f"✏️ Edit Group: {group_name}", wrap='clip')
        
        # Left column: Current members + OK/Cancel (always visible)
        left_section = []
        left_section.append(urwid.Text("Current members (click to remove):"))
        if current_members:
            for member in sorted(current_members):
                member_text = f"  • {member} ✕"
                mbtn = urwid.Button(member_text)
                
                def make_remove_handler(f, g, m):
                    return lambda btn: self._remove_group_member(f, g, m)
                urwid.connect_signal(mbtn, 'click', make_remove_handler(field, group_name, member))
                left_section.append(urwid.AttrMap(mbtn, 'header', focus_map='reversed'))
        else:
            left_section.append(urwid.Text("  (no members)"))
        
        left_section.append(urwid.Divider())
        
        def save_edits(btn):
            new_members = list(current_members)
            for label, cb in cb_widgets.items():
                if cb.get_state() and label not in new_members:
                    new_members.append(label)
            
            if field in self.engine.label_groups:
                self.engine.label_groups[field][group_name] = {"members": new_members}
                self.engine.save_label_groups()
            
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        def cancel_edit(btn):
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        ok_btn = urwid.Button("✓ OK")
        cancel_btn = urwid.Button("✖ Cancel")
        
        urwid.connect_signal(ok_btn, 'click', save_edits)
        urwid.connect_signal(cancel_btn, 'click', cancel_edit)
        
        left_section.append(urwid.Columns([
            urwid.AttrMap(ok_btn, 'header', focus_map='reversed'),
            urwid.AttrMap(cancel_btn, 'header', focus_map='reversed'),
        ]))
        
        left_pile = urwid.Pile(left_section)
        
        # Right column: Available labels to add
        right_section = []
        right_section.append(urwid.Text("Add new labels:"))
        
        cb_widgets = {}
        for label in available_labels:
            cb = urwid.CheckBox(label, state=False)
            cb_widgets[label] = cb
            right_section.append(cb)
        
        right_listbox = urwid.ListBox(urwid.SimpleFocusListWalker(right_section))
        right_listbox_wrap = urwid.BoxAdapter(right_listbox, height=20)
        
        right_pile = urwid.Pile([
            urwid.Text("Add new labels:"),
            right_listbox_wrap,
        ])
        
        # Combine both columns
        main_content = urwid.Columns([
            ('weight', 1, left_pile),
            ('weight', 1, urwid.LineBox(right_pile, title="Available Labels")),
        ])
        
        dialog_content = urwid.Pile([
            ('pack', header),
            ('pack', urwid.Divider()),
            main_content,
        ])
        
        filler = urwid.Filler(dialog_content, valign='top')
        
        edit_box = urwid.LineBox(filler, title="Edit Group")
        
        self.group_overlay = urwid.Overlay(
            edit_box,
            self.layout,
            align='center',
            width=('relative', 80),
            valign='middle',
            height=('relative', 60)
        )
        self.loop.widget = self.group_overlay
        self.loop.draw_screen()

    def _remove_group_member(self, field, group_name, member):
        """Remove a member from a group and refresh the edit dialog."""
        group_data = self.engine.label_groups.get(field, {}).get(group_name, {})
        current_members = group_data.get("members", [])
        
        if member in current_members:
            current_members.remove(member)
            self.engine.label_groups[field][group_name] = {"members": current_members}
            self.engine.save_label_groups()
        
        self._show_edit_group(field, group_name)

    def _show_rename_dialog(self, field, old_name):
        """Show dialog to rename a group."""
        group_data = self.engine.label_groups.get(field, {}).get(old_name, {})
        members = group_data.get("members", [])
        
        dialog_content = []
        
        header = urwid.Text(f"✏️ Rename Group: {old_name}", wrap='clip')
        dialog_content.append(header)
        dialog_content.append(urwid.Divider())
        
        new_name_edit = urwid.Edit("New name: ", old_name)
        dialog_content.append(new_name_edit)
        dialog_content.append(urwid.Divider())
        
        def confirm_rename(btn):
            new_name = new_name_edit.get_edit_text().strip()
            if not new_name or new_name == old_name:
                self._build_group_labels_view()
                self.loop.draw_screen()
                return
            
            # Rename the group (update key, preserve members)
            if field in self.engine.label_groups:
                if old_name in self.engine.label_groups[field]:
                    group_data = self.engine.label_groups[field][old_name]
                    del self.engine.label_groups[field][old_name]
                    self.engine.label_groups[field][new_name] = group_data
                    self.engine.save_label_groups()
                    self.expanded_groups = {}
                    self.build_label_list()
            
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        def cancel_rename(btn):
            self._build_group_labels_view()
            self.loop.draw_screen()
        
        rename_btn = urwid.Button("✓ Rename")
        cancel_btn = urwid.Button("✖ Cancel")
        
        urwid.connect_signal(rename_btn, 'click', confirm_rename)
        urwid.connect_signal(cancel_btn, 'click', cancel_rename)
        
        action_buttons = urwid.Columns([
            urwid.AttrMap(rename_btn, 'header', focus_map='reversed'),
            urwid.AttrMap(cancel_btn, 'header', focus_map='reversed'),
        ])
        dialog_content.append(action_buttons)
        
        pile = urwid.Pile(dialog_content)
        filler = urwid.Filler(pile, valign='top')
        
        rename_box = urwid.LineBox(filler, title="Rename Group")
        
        self.group_overlay = urwid.Overlay(
            rename_box,
            self.layout,
            align='center',
            width=('relative', 50),
            valign='middle',
            height=('relative', 30)
        )
        self.loop.widget = self.group_overlay
        self.loop.draw_screen()

    def toggle_group_expand(self, button, field, group_name):
        key = (field, group_name)
        if key in self.expanded_groups:
            del self.expanded_groups[key]
        else:
            self.expanded_groups[key] = True
        
        self.last_active_category = field
        
        members = self.engine.get_group_members(field, group_name)
        member_keys = [m.lower() for m in members]
        
        # Check if any member is selected in THIS field
        has_member_selected = any((mk, field) in self.selected_labels for mk in member_keys)
        
        if key in self.expanded_groups and not has_member_selected:
            self._build_titles_with_group(field, group_name, members)
        else:
            # Don't rebuild label list - just update titles to preserve focus
            self.update_titles()

    def _build_titles_with_group(self, field, group_name, members):
        """Build titles showing books from ALL group members (OR logic)."""
        walker = self.title_listbox.body
        walker.clear()
        self.last_query_series_map = {}
        
        if not self.engine:
            walker.append(urwid.Text("📘 Select a label to view matching titles."))
            self.build_label_list()
            return
        
        # Build labels by field from current selections (excluding this group)
        # to filter books that match all other selections first
        group_member_set = set(m.lower() for m in members)
        
        # Get base filtered books from other selections (not this group's members)
        other_labels_by_field = {}
        for label, fld in self.selected_labels:
            # Skip labels from this field (the group we're expanding)
            if fld == field and label.lower() in group_member_set:
                continue
            if fld not in other_labels_by_field:
                other_labels_by_field[fld] = []
            other_labels_by_field[fld].append(label)
        
        # If there are other selections, query for them first
        if other_labels_by_field:
            result = self.engine.query(other_labels_by_field)
            base_book_ids = set(result.get("books", {}).keys())
        else:
            # No other selections, start from all books
            base_book_ids = set(self.engine.label_map.keys())
        
        # Now filter base books by group member labels (OR logic within this field)
        all_group_books = set()
        for book_id in base_book_ids:
            info = self.engine.label_map.get(book_id)
            if not info:
                continue
            labels_by_field = info.get("labels_by_field", {})
            field_labels = labels_by_field.get(field, [])
            
            # Check if ANY of the group member labels match
            for label in field_labels:
                if label.lower() in group_member_set:
                    all_group_books.add(book_id)
                    break
        
        # Get the books data
        books = {}
        for book_id in all_group_books:
            info = self.engine.label_map.get(book_id, {})
            data = {
                "series": info.get("series", ""),
                "author": info.get("author", "Unknown")
            }
            books[book_id] = data
        
        # Display the books - separate loop for series and standalone
        # First, collect series entries (all volumes of each series)
        series_entries = {}  # norm_series -> list of volume_entry
        standalone_entries = []  # list of volume_entry for standalone books
        
        for book_id, data in books.items():
            if not data:
                continue
            title = self.engine.label_map.get(book_id, {}).get("title", "").strip()
            raw_series = (data.get("series") or "").strip()
            norm_series = raw_series.lower() if raw_series else None
            author = data.get("author", "Unknown")

            volume_entry = {
                "book_id": book_id,
                "title": title or book_id.split(":")[-1].strip(),
                "author": author,
                "raw_title": title,
                "data": data
            }

            if norm_series:
                # This is a series - collect all volumes
                if norm_series not in series_entries:
                    series_entries[norm_series] = []
                series_entries[norm_series].append(volume_entry)
                # Also populate last_query_series_map for open_series_popup to work
                self.last_query_series_map.setdefault(norm_series, []).append(volume_entry)
            else:
                # This is a standalone book
                standalone_entries.append(volume_entry)
                # Also populate last_query_series_map for open_volume_info to work
                self.last_query_series_map.setdefault(book_id, []).append(volume_entry)
        
        # First, display standalone books
        for volume_entry in standalone_entries:
            display_title = volume_entry.get("title", "")
            author = volume_entry.get("author", "Unknown")
            btn_label = f"📘 {display_title} — Author: {author}"
            btn = urwid.Button(btn_label)
            btn._book_data = volume_entry
            book_id = volume_entry.get("book_id")
            urwid.connect_signal(btn, 'click', self.open_volume_info, user_arg=volume_entry)
            walker.append(urwid.AttrMap(btn, 'title', focus_map='reversed'))
        
        # Then, display series (one button per series)
        for norm_series, volumes in sorted(series_entries.items()):
            first_volume = volumes[0]
            raw_series = (first_volume.get("data", {}).get("series") or "").strip()
            display_title = first_volume.get("title", norm_series)
            author = first_volume.get("author", "Unknown")
            btn_label = f"📗 {display_title} (Series: {raw_series}) — Author: {author}"
            btn = urwid.Button(btn_label)
            urwid.connect_signal(btn, 'click', self.open_series_popup, user_arg=norm_series)
            walker.append(urwid.AttrMap(btn, 'title', focus_map='reversed'))

        if not books:
            walker.append(urwid.Text("📘 No books found in this group."))
        
        self.build_label_list()

    def refresh_suggestions(self):
        if self.feeds_enabled:
            rss_items = self.fetch_rss_suggestions([
                "https://www.theguardian.com/books/rss",
                "https://rss.nytimes.com/services/xml/rss/nyt/Books.xml",
                "https://www.tor.com/feed/",
                "https://lithub.com/feed/",
                "https://www.goodreads.com/blog/feed"
            ])
            self.suggestion_listbox.body[:] = [urwid.Text("📚 Live Suggestions:"), *rss_items]
        else:
            self.suggestion_listbox.body[:] = [urwid.Text("📚 Suggestions are currently disabled.")]
        self.loop.draw_screen()

    def open_link(self, button, link):
        # Display the link in a popup dialog with close button
        from urllib.parse import urlparse
        
        # Truncate link for display - show domain + path snippet
        display_link = self._truncate_link(link)
        
        # Content with the full link and copy button
        link_text = urwid.Text(f"🔗 Full Link:\n{link}\n\n📋 Display: {display_link}\n\nClick 'Copy to save link to ~/RSSFeeds-links.txt", wrap='any')
        
        copy_btn = urwid.Button("📋 Copy to Clipboard")
        close_btn = urwid.Button("✖ Close")
        
        buttons = urwid.Columns([(15, copy_btn), (10, close_btn)])
        
        content = urwid.Pile([link_text, urwid.Divider(), buttons])
        box = urwid.LineBox(content, title="Link Popup")
        
        overlay = urwid.Overlay(
            box, self.layout,
            align='center', width=('relative', 85),
            valign='middle', height=('relative', 40)
        )
        
        # Store link for copy function
        self._current_link = link
        
        def handle_overlay_input(key):
            if key in ('esc', 'q', 'enter'):
                self.loop.widget = self.layout
                self.loop.unhandled_input = self.handle_input
            elif key in ('c', 'C'):
                self._copy_link_to_clipboard()
        
        def on_copy_clicked(btn):
            self._copy_link_to_clipboard()
        
        def on_close_clicked(btn):
            self.loop.widget = self.layout
            self.loop.unhandled_input = self.handle_input
        
        urwid.connect_signal(copy_btn, 'click', on_copy_clicked)
        urwid.connect_signal(close_btn, 'click', on_close_clicked)
        
        self.loop.widget = overlay
        self.loop.unhandled_input = handle_overlay_input

    def _truncate_link(self, link, max_length=50):
        """Truncate a URL for display, showing domain and path snippet."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(link)
            domain = parsed.netloc
            path = parsed.path
            
            # If path is too long, truncate it
            if len(path) > 20:
                path = path[:17] + "..."
            
            result = f"{domain}{path}"
            if len(result) > max_length:
                result = result[:max_length-3] + "..."
            return result
        except:
            # If parsing fails, truncate directly
            if len(link) > max_length:
                return link[:max_length-3] + "..."
            return link

    def _copy_link_to_clipboard(self):
        """Save current link to RSSFeeds-links.txt file."""
        import os
        link = getattr(self, '_current_link', '')
        if not link:
            return
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "RSSFeeds-links.txt")
        try:
            with open(file_path, 'w') as f:
                f.write(link)
            print(f"\n✅ Link saved to RSSFeeds-links.txt")
        except Exception as e:
            print(f"\n⚠️ Could not save link: {e}")
        self.loop.draw_screen()

    def fetch_rss_suggestions(self, urls, max_items=2):
        items = []
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                title = entry.title
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                extracted_link = extract_first_link(summary)
                if extracted_link:
                    link_to_use = extracted_link
                elif link:
                    link_to_use = link
                else:
                    link_to_use = None
                items.append(urwid.Padding(urwid.Text(f"• {title}", wrap='space'), left=1, right=1))
                items.append(urwid.Padding(urwid.Text(re.sub('<.*?>', '', summary.strip()), wrap='space'), left=1, right=1))
                if link_to_use:
                    # Truncate link for display - show domain + path snippet
                    display_link = self._truncate_link(link_to_use)
                    link_btn = urwid.Button(f"📎 {display_link}")
                    urwid.connect_signal(link_btn, 'click', self.open_link, user_arg=link_to_use)
                    items.append(urwid.Padding(urwid.AttrMap(link_btn, 'selected', focus_map='reversed'), left=1, right=1))
                else:
                    items.append(urwid.Padding(urwid.Text("No link found.", wrap='space'), left=1, right=1))
        return items

    def run(self):
        self.loop.run()

# Entry point
if __name__ == "__main__":
    print("🚀 Launching CalibreSynapse Urwid TUI with Enhanced Panels...")
    try:
        CalibreUI().run()
    except Exception as e:
        logging.error("Unhandled exception", exc_info=True)
        print(f"❌ Application crashed: {e}")
