#!/usr/bin/env python3
# v. 1.5
import warnings
#warnings.filterwarnings("ignore", category=DeprecationWarning)
import urwid
import json
import pyfiglet
import itertools
import feedparser
import logging
import re
from CalibreEngine import CalibreEngine
from ComboUsageTracker import ComboUsageTracker

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

        self.themes = {
            "deepsea": [('header', 'dark blue,bold', ''),
                        ('selected', 'light cyan,bold', ''),
                        ('raw', 'dark gray', ''),
                        ('title', 'light blue', ''),
                        ('series', 'white', '')],
            "sunset": [('header', 'dark red,bold', ''),
                       ('selected', 'yellow,bold', ''),
                       ('raw', 'light gray', ''),
                       ('title', 'light magenta', ''),
                       ('series', 'light green', '')]
        }

        self.selected_text = urwid.Text("📖 Welcome to CalibreSynapse — where genre meets depth.")
        self.search_edit = urwid.Edit("🔎 Search Label: ")
        self.label_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.title_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.suggestion_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([
            urwid.Text("📚 Loading suggestions...")
        ]))

        logo_text = pyfiglet.figlet_format("CalibreSynapse")
        self.logo_widget = urwid.Filler(
            urwid.Padding(urwid.Text(logo_text, wrap='clip'), left=2, right=2),
            valign='top'
        )

        self.rotating_book_widget = urwid.Text("")
        footer_text_widget = urwid.Text(
            "🔍 Q: Quit | C: Clear | U: Undo | ↑↓: Navigate | -/+: Page | Enter: Select | T: Toggle Feeds"
            "🟦 Blue = Standalone Book | 🟩 Green = Series"
        )

        undo_btn = urwid.Button("⏪ Undo Last", on_press=self.undo_last_label)
        undo_btn_map = urwid.AttrMap(undo_btn, 'header', focus_map='reversed')

        self.footer = urwid.Columns([
            ('weight', 5, footer_text_widget),
            ('pack', undo_btn_map)
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
        self.loop = urwid.MainLoop(self.layout, palette=self.themes[self.current_theme], unhandled_input=self.handle_input)
        self.build_theme_bar()
        self.frame_gen = self.book_frames()
        self.loop.set_alarm_in(0.1, self.animate_book)
        self.loop.set_alarm_in(0.2, lambda loop, data: self.refresh_suggestions())

        self.build_label_list()
        self.update_titles()

    def undo_last_label(self, button):
        if self.selected_labels:
            last = sorted(self.selected_labels)[-1]
            self.selected_labels.remove(last)
            print(f"⏪ Removed last label: {last}")
            self.update_selected()
            self.update_titles()

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

        label_counts = {lbl.lower(): count for lbl, count in refinement.get(field, [])}
        filtered = []
        for label in sorted(split_labels):
            key = label.lower()
            if key in self.selected_labels:
                filtered.append(label)
                continue
            if self.search_query and self.search_query not in key:
                continue
            if self.selected_labels and key not in label_counts:
                continue
            filtered.append(label)

        self._filtered_label_cache[cache_key] = filtered
        return filtered
    def build_label_list(self, restore_focus_position=None, refinement=None):
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
            label_counts = {lbl.lower(): count for lbl, count in refinement.get(field, [])}
            pages = self.get_paginated_labels(field, filtered_labels)

            if not pages:
                walker.append(urwid.Text("⚠️ No labels to display in this category."))
                continue

            page_index = self.category_page_index.get(field, 0)
            page_index = min(page_index, len(pages) - 1)
            self.category_page_index[field] = page_index
            current_page = pages[page_index]

            for label in current_page:
                key = label.lower()
                is_selected = key in self.selected_labels
                count = label_counts.get(key, "")
                count_str = f" ({count})" if count else ""
                label_text = f"  • {label}{count_str}"
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
        else:
            self.selected_labels.add(label)
        self.update_selected()
        self.update_titles()

    def select_from_search(self, button, label):
        self.search_query = ""
        self.search_edit.set_edit_text("")
        self.selected_labels.add(label)
        self.update_selected()
        self.update_titles()

    def perform_search(self, query):
        self.search_query = query
        if not self.engine:
            self.label_listbox.body[:] = [urwid.Text("❌ Engine not initialized.")]
            return

        result = self.engine.query(list(self.selected_labels))
        refinable = result.get("refinable_labels", {})
        compatible_labels = [
            (label, category)
            for category, label_list in refinable.items()
            for label, _ in label_list
        ]

        matches = [(label, category) for label, category in compatible_labels if query.lower() in label.lower()]

        if matches:
            self.label_listbox.body[:] = [urwid.Text(f"🔍 Results for '{query}':")]
            for label, category in matches:
                label_text = f"• {label} ({category})"
                btn = urwid.Button(label_text)
                urwid.connect_signal(btn, 'click', self.select_from_search, user_arg=label.lower())
                self.label_listbox.body.append(urwid.AttrMap(btn, 'raw', focus_map='reversed'))
        else:
            self.label_listbox.body[:] = [urwid.Text("🔍 No direct match, but here are compatible labels:")]
            for label, category in compatible_labels:
                label_text = f"• {label} ({category})"
                btn = urwid.Button(label_text)
                urwid.connect_signal(btn, 'click', self.select_from_search, user_arg=label.lower())
                self.label_listbox.body.append(urwid.AttrMap(btn, 'raw', focus_map='reversed'))

    def paginate_labels(self, labels, page_size):
        for i in range(0, len(labels), page_size):
            yield labels[i:i + page_size]

    def paginate(self, entries, page_size):
        for i in range(0, len(entries), page_size):
            yield entries[i:i + page_size]

    def update_titles(self):
        walker = self.title_listbox.body
        walker.clear()

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

        for book_id, data in books.items():
            if not data:
                continue

            title = self.engine.label_map.get(book_id, {}).get("title", "").strip()
            raw_series = (data.get("series") or "").strip()
            norm_series = raw_series.lower() if raw_series else None
            author = data.get("author", "Unknown")

            if norm_series and norm_series in seen_series:
                continue
            if norm_series:
                seen_series.add(norm_series)

            if not title:
                title = book_id.split(":")[-1].strip()
                title = re.sub(r'\(\d+\)$', '', title).strip()

            if title and raw_series:
                walker.append(urwid.Text(("title", f"📗 {title} (Series: {raw_series}) — Author: {author}")))
            elif title:
                walker.append(urwid.Text(("title", f"📘 {title} — Author: {author}")))
            elif raw_series:
                walker.append(urwid.Text(("series", f"📚 Series: {raw_series}) — Author: {author}")))
    def build_body(self):
        left_column = urwid.LineBox(self.label_listbox, title="📂 Labels")

        main_right = urwid.Columns([
            ('weight', 2, urwid.Pile([
                ('weight', 3, urwid.LineBox(self.title_listbox, title="📚 Titles")),
                ('pack', urwid.Columns([
                    ('weight', 3, self.logo_widget),
                    ('pack', self.rotating_book_widget)
                ]))
            ])),
            ('weight', 1, urwid.LineBox(self.suggestion_listbox, title="📰 Book Feeds"))
        ])

        return urwid.Columns([
            ('weight', 1, left_column),
            ('weight', 2, main_right)
        ])

    def book_frames(self):
        frames = ["📘", "📗", "📙", "📕", "📓", "📔", "📒", "📚"]
        return itertools.cycle(frames)

    def animate_book(self, loop, user_data):
        self.rotating_book_widget.set_text(next(self.frame_gen))
        loop.set_alarm_in(0.1, self.animate_book)

    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key in ('c', 'C'):
            self.selected_labels.clear()
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

    def fetch_rss_suggestions(self, urls, max_items=2):
        items = []
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                title = entry.title
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                items.append(urwid.Text(f"• {title}", wrap='any'))
                items.append(urwid.Text(summary.strip(), wrap='any'))
                items.append(urwid.Text(link, wrap='any'))
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
