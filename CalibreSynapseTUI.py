#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import urwid
import json
import pyfiglet
import itertools
import feedparser
import logging
import re
from CalibreEngine import CalibreEngine

# Setup logging to file
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

        self.selected_labels = set()
        self.expanded_categories = {}
        self.search_query = ""
        self.current_theme = "deepsea"
        self.feeds_enabled = True

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
        self.footer = urwid.Text(
            "🔍 Q: Quit | C: Clear | ↑↓: Navigate | Enter: Select | T: Toggle Feeds"
            "🟦 Blue = Standalone Book | 🟩 Green = Series"
        )

        self.theme_bar = urwid.Columns([
            urwid.AttrMap(urwid.Button(name, on_press=self.switch_theme, user_data=name), 'header')
            for name in self.themes.keys()
        ])

        self.toggle_btn = urwid.Button("🛑 Toggle Feeds", on_press=self.toggle_feeds)
        toggle_row = urwid.Columns([
            urwid.AttrMap(self.toggle_btn, 'header')
        ])

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
        self.frame_gen = self.book_frames()
        self.loop.set_alarm_in(0.1, self.animate_book)
        self.loop.set_alarm_in(0.2, lambda loop, data: self.refresh_suggestions())

        self.build_label_list()
        self.update_titles()

    def switch_theme(self, button, theme_name):
        if theme_name in self.themes:
            self.current_theme = theme_name
            self.loop.screen.clear()
            self.loop.screen.register_palette(self.themes[theme_name])
            self.loop.draw_screen()

    def update_selected(self):
        if self.selected_labels:
            self.selected_text.set_text("🎯 Selected Labels: " + ", ".join(sorted(self.selected_labels)))
        else:
            self.selected_text.set_text("📖 Welcome to CalibreSynapse — where genre meets depth.")

    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key in ('c', 'C'):
            self.selected_labels.clear()
            self.search_query = ""
            self.search_edit.set_edit_text("")
            self.update_selected()
            self.update_titles()
            self.build_label_list()
        elif key in ('t', 'T'):
            self.toggle_feeds(None)
        elif key == 'enter':
            query = self.search_edit.edit_text.strip()
            self.perform_search(query)

    def run(self):
        self.loop.run()

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
        frames = [
            "📘", "📗", "📙", "📕", "📓", "📔", "📒", "📚"
        ]
        return itertools.cycle(frames)

    def animate_book(self, loop, user_data):
        self.rotating_book_widget.set_text(next(self.frame_gen))
        loop.set_alarm_in(0.1, self.animate_book)

    def on_search_keypress(self, edit, key):
        if key == 'enter':
            query = edit.edit_text.strip()
            self.perform_search(query)

    def perform_search(self, query):
        self.search_query = query
        if not self.engine:
            self.label_listbox.body[:] = [urwid.Text("❌ Engine not initialized.")]
            return

        results = []
        label_to_category = self.engine.label_to_category

        for field in self.engine.dynamic_vocab:
            for label in self.engine.dynamic_vocab[field]:
                if query.lower() in label.lower():
                    category = label_to_category.get(label.lower(), "Unknown")
                    label_text = f"• {label} ({category})"
                    btn = urwid.Button(label_text)
                    urwid.connect_signal(btn, 'click', self.select_from_search, user_arg=label.lower())
                    results.append(urwid.AttrMap(btn, 'raw', focus_map='reversed'))

        if results:
            self.label_listbox.body[:] = [urwid.Text(f"🔍 Results for '{query}':")] + results
        else:
            self.label_listbox.body[:] = [urwid.Text(f"❌ No matches for '{query}'")]

    def select_from_search(self, button, label):
        self.search_query = ""
        self.search_edit.set_edit_text("")
        self.selected_labels.add(label)
        self.update_selected()
        self.update_titles()
        self.build_label_list()

    def toggle_label_direct(self, label):
        key = label.lower()
        if not self.engine:
            return

        all_labels = set()
        for field in self.engine.dynamic_vocab:
            all_labels.update([lbl.lower() for lbl in self.engine.dynamic_vocab[field]])
        if key in all_labels:
            if key in self.selected_labels:
                self.selected_labels.remove(key)
            else:
                self.selected_labels.add(key)
            self.update_selected()
            self.update_titles()
            self.build_label_list()

    def build_label_list(self):
        walker = self.label_listbox.body
        walker.clear()

        if not self.engine:
            walker.append(urwid.Text("❌ Engine not initialized."))
            return

        all_fields = sorted(self.engine.dynamic_vocab.keys())
        refinement = {}
        if self.selected_labels:
            result = self.engine.query(list(self.selected_labels))
            refinement = result.get("refinable_labels", {})

        for field in all_fields:
            is_expanded = self.expanded_categories.get(field, False)
            toggle = "▼" if is_expanded else "▶"
            header_btn = urwid.Button(f"{toggle} {field}")
            urwid.connect_signal(header_btn, 'click', self.toggle_category, user_arg=field)
            walker.append(urwid.AttrMap(header_btn, 'header'))

            if not is_expanded:
                continue

            labels_info = self.engine.get_labels_for_field(field)
            raw = labels_info.get("raw", [])

            walker.append(urwid.Text("─" * 40))

            split_labels = []
            for label in raw:
                if field == "Subject":
                    split_labels.extend([v.strip() for v in label.split(",") if v.strip()])
                else:
                    split_labels.append(label.strip())

            for label in sorted(split_labels):
                key = label.lower()
                is_selected = key in self.selected_labels

                if self.search_query and self.search_query not in key:
                    continue

                if self.selected_labels and not is_selected:
                    if field not in refinement:
                        continue
                    refinable_keys = {lbl.lower() for lbl, _ in refinement[field]}
                    if key not in refinable_keys:
                        continue

                count = ""
                for ref_label, ref_count in refinement.get(field, []):
                    if ref_label.lower() == key:
                        count = f" ({ref_count})"
                        break

                label_text = f"  • {label}{count}"
                btn = urwid.Button(label_text)
                urwid.connect_signal(btn, 'click', self.toggle_label, user_arg=key)
                style = 'selected' if is_selected else 'raw'
                walker.append(urwid.AttrMap(btn, style, focus_map='reversed'))

    def toggle_category(self, button, field):
        self.expanded_categories[field] = not self.expanded_categories.get(field, False)
        self.build_label_list()

    def toggle_label(self, button, label):
        if label in self.selected_labels:
            self.selected_labels.remove(label)
        else:
            self.selected_labels.add(label)
        self.update_selected()
        self.update_titles()
        self.build_label_list()

    def update_titles(self):
        walker = self.title_listbox.body
        walker.clear()

        if not self.selected_labels:
            walker.append(urwid.Text("📘 Select a label to view matching titles."))
            return

        if not self.engine:
            walker.append(urwid.Text("❌ Engine not initialized."))
            return

        result = self.engine.query(list(self.selected_labels))
        books = result.get("books", {})
        seen_series = set()
        count = 0

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

            if count >= 50:
                break

            if title and raw_series:
                walker.append(urwid.Text(("title", f"📗 {title} (Series: {raw_series}) — Author: {author}")))
            elif title:
                walker.append(urwid.Text(("title", f"📘 {title} — Author: {author}")))
            elif raw_series:
                walker.append(urwid.Text(("series", f"📚 Series: {raw_series}) — Author: {author}")))

            count += 1

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
# Entry point
if __name__ == "__main__":
    print("🚀 Launching CalibreSynapse Urwid TUI with Enhanced Panels...")
    try:
        CalibreUI().run()
    except Exception as e:
        logging.error("Unhandled exception", exc_info=True)
        print(f"❌ Application crashed: {e}")
