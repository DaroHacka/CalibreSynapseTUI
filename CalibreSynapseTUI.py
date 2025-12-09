
#!/usr/bin/env python3
# v. 1.6.2 (patched + clock)
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
    filename='calibre_ui.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CalibreUI:
    def __init__(self):
        try:
            self.engine = CalibreEngine(
                label_map_path="semantic_label_map.json",
                vocab_path="dynamic_vocabulary.json",
                parser_path="vocabulary_parser.json"
            )
        except Exception as e:
            print(f"❌ Engine failed: {e}")
            self.engine = None

        self.in_search_mode = False
        self.usage_tracker = ComboUsageTracker()
        self._split_cache = {}
        self._page_cache = {}
        self._refinement_cache = {}
        self._filtered_label_cache = {}

        self.selected_labels = set()
        self.expanded_categories = {}
        self.search_query = ""
        self.current_theme = "deepsea"
        self.feeds_enabled = True
        self.label_page_size = 30
        self.category_page_index = {}
        self.last_active_category = None
        self.selected_labels_order = [] # undo related

        # store last query result books mapping for series expansion and lookups
        self.last_query_series_map = {}

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
        footer_text_widget = urwid.Text(
            "🔍 Q: Quit | C: Clear | U: Undo | Esc, P: Close RSS Pop-up | ↑↓: Navigate | -/+: Page | Enter: Select | T: Toggle Feeds"
            "🟦 Blue = Standalone Book | 🟩 Green = Series"
        )

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
        toggle_row = urwid.Columns([
            urwid.AttrMap(self.toggle_btn, 'header')
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

    def undo_last_label(self, button):
        if self.selected_labels_order:
            last = self.selected_labels_order.pop()
            self.selected_labels.remove(last)
            print(f"⏪ Removed last label: {last}")
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
        combo_key = ",".join(sorted(self.selected_labels))
        cache_key = (field, combo_key)
        if cache_key in self._filtered_label_cache:
            return self._filtered_label_cache[cache_key]

        result = self.usage_tracker.get(combo_key)
        if not result:
            result = self.engine.query(list(self.selected_labels))
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
            if key in self.selected_labels:
                filtered.append(label)
                continue
            if self.search_query and self.search_query not in key:
                continue
            if self.selected_labels and key not in label_set:
                continue
            filtered.append(label)

        self._filtered_label_cache[cache_key] = filtered
        return filtered

    def compute_label_counts(self, field, refinement):
        """
        Produce a mapping of label (lowercase) -> count.

        Strategy:
        - If refinement contains explicit counts for this field, use them as base.
        - Otherwise, fall back to scanning engine.label_map and counting:
            - If an item belongs to a series, count that series as 1 for the label (regardless of how many volumes).
            - If an item does NOT belong to a series, count it per book id.
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

        for book_id, info in self.engine.label_map.items():
            labels_by_field = info.get("labels_by_field", {})
            label_values = labels_by_field.get(field, [])
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
                combo_key = ",".join(sorted(self.selected_labels))
                refinement = self._refinement_cache.get(combo_key, {})
            else:
                refinement = {}

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

            filtered_labels = self.get_filtered_labels(field, split_labels, refinement)
            # compute counts with series collapsed to 1
            label_counts = self.compute_label_counts(field, refinement)
            pages = self.get_paginated_labels(field, filtered_labels)

            if not pages:
                walker.append(urwid.Text("⚠️ No labels to display in this category."))
                walker.append(urwid.Divider())  # <-- Always add a divider
                continue

            page_index = self.category_page_index.get(field, 0)
            page_index = min(page_index, len(pages) - 1)
            self.category_page_index[field] = page_index
            current_page = pages[page_index]

            for label in current_page:
                key = label.lower()
                is_selected = key in self.selected_labels
                count = label_counts.get(key, 0)
                # show count only when >0, otherwise leave empty
                count_str = f" ({count})" if count > 0 else ""
                label_text = f"  • {self.strip_suffix(label)}{count_str}"
                btn = urwid.Button(label_text)
                btn._category = field
                urwid.connect_signal(btn, 'click', self.toggle_label, user_arg=key)
                style = 'selected' if is_selected else 'raw'
                walker.append(urwid.AttrMap(btn, style, focus_map='reversed'))

            nav_buttons = []
            if page_index > 0:
                prev_btn = urwid.Button("← Prev", on_press=self.prev_category_page, user_data=field)
                nav_buttons.append(urwid.AttrMap(prev_btn, 'header', focus_map='reversed'))

            if page_index < len(pages) - 1:
                next_btn = urwid.Button("Next →", on_press=self.next_category_page, user_data=field)
                nav_buttons.append(urwid.AttrMap(next_btn, 'header', focus_map='reversed'))

            page_info = urwid.Text(f"📄 Page {page_index + 1} of {len(pages)}")
            walker.append(urwid.Columns(nav_buttons + [page_info]))
            walker.append(urwid.Divider())

        if restore_focus_position is not None:
            try:
                self.label_listbox.focus_position = restore_focus_position
            except IndexError:
                pass

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
        base = focus_widget.base_widget
        if hasattr(base, '_category'):
            return base._category
        if isinstance(base, urwid.Button):
            label = base.get_label()
            match = re.match(r"[▶▼] (.+)", label)
            if match:
                return match.group(1)
        return self.last_active_category

    def toggle_category(self, button, field):
        self.expanded_categories[field] = not self.expanded_categories.get(field, False)
        if self.expanded_categories[field]:
            self.last_active_category = field
            self.build_label_list()
        else:
            self.remove_category_widgets(field)

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

    def toggle_label(self, button, label):
        if label in self.selected_labels:
            self.selected_labels.remove(label)
            if label in self.selected_labels_order:
                self.selected_labels_order.remove(label)
        else:
            self.selected_labels.add(label)
            if label not in self.selected_labels_order:
                self.selected_labels_order.append(label)
        self.update_selected()
        self.update_titles()

    def select_from_search(self, button, label):
        """When user selects a label from search, add it and restore normal UI."""
        self.search_query = ""
        self.search_edit.set_edit_text("")
        self.selected_labels.add(label)
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
                urwid.connect_signal(btn, 'click', self.select_from_search, user_arg=label.lower())
                self.label_listbox.body.append(urwid.AttrMap(btn, 'raw', focus_map='reversed'))
        else:
            self.label_listbox.body[:] = [urwid.Text(f"🔍 No results for '{query}'.")]

    def paginate_labels(self, labels, page_size):
        for i in range(0, len(labels), page_size):
            yield labels[i:i + page_size]

    def paginate(self, entries, page_size):
        for i in range(0, len(entries), page_size):
            yield entries[i:i + page_size]

    def update_titles(self):
        walker = self.title_listbox.body
        walker.clear()

        # reset series map for this query
        self.last_query_series_map = {}

        if not self.selected_labels or not self.engine:
            walker.append(urwid.Text("📘 Select a label to view matching titles."))
            self.build_label_list()
            return

        combo_key = ",".join(sorted(self.selected_labels))
        cached = self.usage_tracker.get(combo_key)

        if cached:
            print(f"🧠 Cache hit for {combo_key}")
            result = cached
        else:
            print(f"🔄 Live query for {combo_key}")
            result = self.engine.query(list(self.selected_labels))
            self.usage_tracker.store(combo_key, result)

        refinement = result.get("refinable_labels", {})
        self._refinement_cache[combo_key] = refinement
        self.build_label_list(refinement=refinement)

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
                self.toggle_label(None, label_clean)
                self.build_label_list(restore_focus_position=focus_position)
        elif key in ('-', '+'):
            field = self.get_focused_category()
            if field:
                focus_position = self.label_listbox.focus_position
                if key == '+':
                    self.next_category_page(field=field)
                elif key == '-':
                    self.prev_category_page(field=field)
                self.build_label_list(restore_focus_position=focus_position)

    def update_selected(self):
        if self.selected_labels:
            self.selected_text.set_text("🎯 Selected Labels: " + ", ".join(sorted(self.selected_labels)))
        else:
            self.selected_text.set_text("📖 Welcome to CalibreSynapse — where genre meets depth.")

    def toggle_feeds(self, button):
        self.feeds_enabled = not self.feeds_enabled
        self.refresh_suggestions()

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
    # Display the link in a popup dialog
        link_message = urwid.LineBox(
            urwid.Text(f"🔗 Link:\n{link}\n\nSelect and copy with your mouse/terminal.")
        )
        overlay = urwid.Overlay(
            link_message, self.layout,
            align='center', width=('relative', 90),
            valign='middle', height=('relative', 30)
        )
        self.loop.widget = overlay
        # Press any key to dismiss
        def dismiss(key):
            if key in ('esc', 'p'):
                self.loop.widget = self.layout
                self.loop.unhandled_input = self.handle_input

        self.loop.screen.register_palette(self.themes[self.current_theme])  # Refresh colors
        self.loop.unhandled_input = dismiss

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
                items.append(urwid.Text(f"• {title}", wrap='any'))
                items.append(urwid.Text(re.sub('<.*?>', '', summary.strip()), wrap='any'))
                if link_to_use:
                    link_btn = urwid.Button(link_to_use)
                    urwid.connect_signal(link_btn, 'click', self.open_link, user_arg=link_to_use)
                    items.append(urwid.AttrMap(link_btn, 'selected', focus_map='reversed'))
                else:
                    items.append(urwid.Text("No link found.", wrap='any'))
        return items

    def open_link(self, button, link):
        link_message = urwid.LineBox(urwid.Text(f"🔗 Link:\n{link}\n\nSelect and copy with your mouse/terminal.", wrap='clip'))
        overlay = urwid.Overlay(link_message, self.layout,
                            align='center', width=('relative', 60),
                            valign='middle', height=('relative', 30))
        self.loop.widget = overlay
        def dismiss(key):
            self.loop.widget = self.layout
            self.loop.unhandled_input = self.handle_input  # Restore default handler!
        self.loop.unhandled_input = dismiss

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
