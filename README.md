# 📚 CalSynTUI+

**CalibreSynapseTUI** is a semantic metadata explorer for Calibre libraries. It's a graphical terminal interface that lets you explore your book collection using custom metadata labels — with menus, panels, and.

---

## 🚀 Features

- keyboard/mouse navigation 🎨 **Interactive TUI** — Graphical terminal interface with keyboard and mouse support
- 🏷️ **Group Labels** — Press `G` to create groups of related labels (e.g., "dual lens" = "dual lens" + "dual pov" + "dual-pv")
- 🔍 **Semantic Search** — Query your library by emotional tone, pacing, themes, genres, and more
- 📊 **Smart Filtering** — Labels show only compatible options based on your selections
- 🔗 **Discover Connections** — Find hidden connections between books you already own
- 💾 **Fully Offline** — Your data stays local, privacy-respecting

---

## 📋 Prerequisites

| Requirement | Description |
|-------------|-------------|
| 🐍 Python 3.8+ | Run `python3 --version` to check |
| 📖 Calibre | Required for library management |
| 🌐 Calibre Server | Must be running to serve your library |

---

## 🛠️ Installation

### Option 1: Automated Installer

```bash
# Clone or download this repository
cd CalSynTUI+

# Run the installer
./install.sh
```

### Option 2: Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Make launcher executable
chmod +x CalSynTUI+

# Run the app
./CalSynTUI+
```

---

## 📖 Step-by-Step Setup Guide

Follow these steps to get CalSynTUI+ working with your Calibre library:

### Step 1: Create Custom Columns in Calibre

Before adding metadata, you need to define your **fields** (categories):

1. Open **Calibre** → **Preferences** → **Add your own columns**
2. Create columns for each metadata category you want to track:

   | Column Name | Lookup Name | Type |
   |-------------|-------------|------|
   | Genres | `#genres` | Tag |
   | Provenance | `#provenance` | Tag |
   | Writing Style | `#writing_style` | Tag |
   | Emotional Tone | `#emotional_tone` | Tag |
   | Character Traits | `#character_traits` | Tag |
   | Book Setting | `#book_setting` | Tag |
   | Reading Mood | `#reading_mood` | Tag |
   | Perspective | `#perspective` | Tag |
   | Pacing | `#pacing` | Tag |
   | Themes | `#themes` | Tag |
   | ... | ... | ... |

> ⚠️ **Important**: The column names must match exactly in Calibre and CalSynTUI+

---

### Step 2: Import Books to Calibre

Use the included import script to add books:

```bash
./cimport.sh
```

- Choose `single` to import one file
- Choose `multi` to import a folder of books

> 🔧 **Configuration**: Edit `cimport.sh` and replace the `CALIBRE_LIB` path with your own Calibre Library path:

```bash
CALIBRE_LIB="/path/to/your/Calibre Library"
```

---

### Step 3: Generate Metadata with AI

This is the key step — you'll use AI to generate rich metadata for your books:

1. **Copy the rules**: Read `set_of_rules.txt` — this contains all the curation guidelines
2. **Prepare the form**: Open `form.txt` — this is your template
3. **Send to AI**: Send BOTH files to an AI assistant (Gemini, ChatGPT, Copilot, etc.)

   > 🤖 **Prompt example**:
   > "Here are my curation rules and a form template. For each book in my library, please fill in the metadata fields based on the book's content. The books are: [list your books with their Calibre IDs]"

4. **AI fills the form**: The AI will return commands like:

   ```bash
   calibredb set_metadata 123 \
     --with-library "/path/to/library" \
     --field "#genres: mystery, crime" \
     --field "#provenance: usa" \
     --field "#pacing: fast" \
     ...
   ```

---

### Step 4: Apply Metadata to Calibre

1. **Edit the path**: Open the AI-generated commands and replace my Calibre Library path with YOUR path:

   ```bash
   --with-library "/path/to/YOUR/Calibre Library"
   ```

2. **Run the commands**: Execute each command in your terminal

---

### Step 5: Build the Semantic Index

Now generate the search index:

```bash
python3 Semantic_Compatibility_Matrix_Builder.py
```

This creates:
- 📊 `semantic_label_map.json` — Your book database
- 📚 `dynamic_vocabulary.json` — Available labels by field

---

### Step 6: Launch CalSynTUI+

```bash
./CalSynTUI+
```

> 🎉 Your metadata will now populate the interface! Browse labels, filter books, and discover new reads.

---

## 🔧 Maintenance

### Label Disambiguator

Some labels appear in multiple fields (e.g., "france" in Provenance AND Setting). CalSynTUI+ needs to distinguish them:

| Field | Suffix | Example |
|-------|--------|---------|
| `#provenance` | `-p` | `france-p` |
| `#book_setting` | `-bs` | `france-bs` |
| `#writing_style` | `-ws` | `slow-ws` |
| `#ppc` | `slow-pc`acing` | `- |

Run the disambiguator periodically:

```bash
python3 label_disambiguator.py
```

> 🔧 **Configuration**: Edit `label_disambiguator.py` and set your library path:

```python
library_path = "/path/to/your/Calibre Library"
```

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` `↓` | Navigate labels |
| `Enter` | Select/expand label |
| `Space` | Toggle label |
| `G` | Open Group Labels menu |
| `C` | Clear all selections |
| `T` | Toggle RSS feeds |
| `U` | Undo last label |
| `Q` | Quit |

---

## 📁 File Structure

```
CalSynTUI+/
├── CalibreSynapseTUI.py    # Main TUI application
├── CalibreEngine.py        # Calibre query engine
├── ComboUsageTracker.py    # Query cache
├── Semantic_Compatibility_Matrix_Builder.py  # Build index
├── label_disambiguator.py  # Fix label suffixes
├── cimport.sh              # Book import script
├── CalSynTUI+              # Launcher
├── install.sh              # Installer
├── requirements.txt        # Dependencies
├── set_of_rules.txt        # AI curation rules
├── form.txt                # Metadata template
├── Demo-Database/          # Sample data for testing
└── README.md               # This file
```

---

## 🎯 Demo Mode

Want to try CalSynTUI+ first? Use the included demo database:

```bash
# Copy demo data to the main folder
cp Demo-Database/*.json ./

# Launch
./CalSynTUI+
```

This lets you explore the interface with sample data before connecting to your own library.

---

## 🤝 Credits

Built with ❤️ using Python and [urwid](https://urwid.org/) for the terminal interface.

---

<p align="center">
  <img src="https://github.com/DaroHacka/CalibreSynapseTUI/raw/main/Screenshot 2026-02-27 231532.png" alt="CalSynTUI+ Screenshot" width="600"/>
</p>
