# 🎨 CalibreSynapseTUI

**CalibreSynapseTUI** is the graphical terminal interface for CalibreSynapse. It builds on the CLI version by offering a rich, interactive Text User Interface (TUI) that lets users explore semantic metadata visually — with menus, panels, and keyboard/mouse navigation.

The TUI framework is implemented using Python’s `urwid` library, allowing for a responsive, scrollable, and fully interactive experience inside the terminal. This graphical layer transforms the way you filter and refine your book searches: instead of typing commands, you can navigate through expandable fields, toggle labels, and visually explore your library’s semantic landscape.

Read full detailed guide here: https://github.com/DaroHacka/CalibreSynapseCLI/blob/main/README.md
---

## 🚀 Features

<table>
  <tr>
    <td width="160">
      <img src="https://github.com/DaroHacka/CalibreSynapseCLI/blob/main/logo%20for%20CalibreSyna.png?raw=true" alt="CalibreSynapseCLI Logo" width="150"/>
    </td>
    <td>
      <ul>
        <li>Graphical terminal interface with keyboard and mouse support</li>
        <li>Query your Calibre library by emotional tone, pacing, themes, genres, and more</li>
        <li>Build a semantic compatibility matrix from your custom metadata</li>
        <li>Use AI to generate nuanced labels for each book</li>
        <li>Discover hidden connections between books you already own</li>
        <li>Fully offline and privacy-respecting</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🛠️ Requirements

To run CalibreSynapseCLI on Linux:

- Python 3  
- Calibre Server installed and running  
- Python packages:
  ```bash
  pip install pyfiglet feedparser urwid
  ```

---

## 📁 Files Included

- `CalibreSynapse.py` — the interactive CLI interface  
- `Semantic_Compatibility_Matrix_Builder.py` — builds the semantic index  
- `config.json` — sample configuration for paths and metadata fields  
- `sample_metadata_prompt.txt` — example prompt for AI-assisted label generation
- `calibre_import.sh` — calibre book import script
- `sample_generated_files.txt` — Want to see how the output files from semantic_compatibility_matrix_builder.py are structured? Check out the included sample.


## 📥 Book Import Script

You need this file to easily upload digital books into your Calibre Library via terminal  
./calibre_import  
Do you want to import a single file or multiple files? (Type: single / multi)  
insert path:

## 🔍 How CalibreSynapse Works

CalibreSynapse isn’t just a metadata tool — it’s a **semantic search engine** for your personal library. Think of your labels as forming a vast constellation:  
- Some are **isolated islands**, representing niche moods or rare themes  
- Others form **small atolls**, clusters of books that share a few traits  
- And some belong to **large conglomerates**, densely connected genres or emotional tones

When you select a label, CalibreSynapse instantly filters out all incompatible ones. What remains are only those labels that **coexist** with your current selection — forming a dynamic map of possibilities. You can switch labels freely, exploring combinations that reflect your **mood**, **memories**, or **curiosities**.

Each label displays a number — the count of books that match your current selection when that label is added. This lets you refine your search intuitively, guided by compatibility rather than rigid categories.

Books are visually distinguished:
- 🟦 **Standalone books** appear in one color  
- 🟨 **Series** are shown in another, so you can track narrative arcs or thematic continuities

It’s the kind of search engine you use while sipping a warm cup of coffee or maybe tea, reflecting on what you’d like to read next, especially when you're not following any specific reading program and just want something undefined or unexpected.  
In my case, it mirrors the books I actually own, but I guess it could also be used for books you don’t have yet, maybe even your local library’s catalogue. I guess I could add a wishlist  to CalibreSynapse if I wanted to.

---

<p align="center">
  <img src="https://github.com/DaroHacka/CalibreSynapseTUI/blob/main/CalibreSynapseTUI%20dashboard.png?raw=true" alt="CalibreSynapseTUI Dashboard">
</p>

## 🖥️ TUI-Specific Enhancements

The TUI version introduces several new features that elevate the experience:

1. **Personalized Theme**  
   Customize the color palette and layout to match your aesthetic or accessibility needs.

2. **Live Book Suggestions via RSS Feeds**  
   Toggle real-time suggestions from external sources like:
   - [Goodreads](https://www.goodreads.com)  
   - [The StoryGraph](https://app.thestorygraph.com)  
   - [Literary Hub](https://lithub.com)  
   - [Book Riot](https://bookriot.com)

3. **Search Bar**  
   Type a label directly if you know what you're looking for — no need to scroll.

4. **Select/Deselect Feature**  
   Click or press to toggle labels on and off, refining your query in real time.

5. **Expandable and Collapsible Fields**  
   Browse metadata categories like “Themes” or “Emotional Tone” without clutter.

6. **Keyboard Shortcuts**  
   Navigate quickly using intuitive key bindings (e.g. `Tab`, `Enter`, `Esc`, `Space`).

7. **Mouse Integration**  
   Scroll through lists, click to select labels, and interact with the interface naturally.

---

## 🛠️ Requirements

To run CalibreSynapseTUI on Linux:

- Python 3  
- Calibre Server installed and running  
- Python packages:
  ```bash
  pip install pyfiglet feedparser urwid
  ```

---

## 📁 Files Included

- `CalibreSynapseTUI.py` — the TUI engine and main entry point  
- `CalibreSynapse.py` — CLI logic and label query engine  
- `Semantic_Compatibility_Matrix_Builder.py` — builds the semantic index  
- `sample_metadata_prompt.txt` — example prompt for AI-assisted label generation  
- `logo for CalibreSyna.png` — project logo (optional for branding)

---

## ⚙️ Setup Instructions

The setup process is identical to the CLI version. Here's a condensed guide:

### 1. Create Composite Metadata Columns in Calibre

Use Calibre Desktop or SQLite to define custom fields like `#themes`, `#emotional_tone`, `#book_setting`, etc.  
Ensure fields are **composite**, not atomic — so labels like `rebellious, brave, romantic` are treated as separate entries.

### 2. Inspect Column Names via SQLite

```bash
sqlite3 /path/to/metadata.db
SELECT rowid, label, name, datatype FROM custom_columns ORDER BY rowid;
```

Use this to match internal column names (e.g. `#genre`, `#themes`) with your Calibre setup.

### 3. Edit the Semantic Matrix Builder

Update paths and column names in `Semantic_Compatibility_Matrix_Builder.py` to match your system.

### 4. Generate Semantic Labels

Use the AI prompt in `sample_metadata_prompt.txt` to generate structured labels. Follow formatting rules:
- Use commas, not "and"
- Keep labels short (1–3 words)
- Use generalized settings like `"village"` or `"urban district"`
- Add author bio and book description with emoticons in the comments field

### 5. Inject Metadata into Calibre

Use `calibredb set_metadata` with your book ID and field values. Example:

```bash
calibredb set_metadata 123 \
  --with-library "/home/user/Calibre Library/" \
  --field "#themes: existential dread, redemption" \
  --field "#book_setting: Japan, urban district" \
  --field "comments: 📘 A surreal journey through memory and loss..."
```

### 6. Run the Semantic Matrix Builder

This will generate:
- `semantic_label_map.json`  
- `dynamic_vocabulary.json`  
- `vocabulary_parser.json`  
- `label_frequency.json`  
- `flat_label_index.json`

### 7. Launch CalibreSynapseTUI

```bash
python CalibreSynapseTUI.py
```
<p align="center">
  <img src="https://raw.githubusercontent.com/DaroHacka/CalibreSynapseTUI/refs/heads/main/Screenshot%202025-10-03%20005521.png" alt="CalibreSynapseTUI Dashboard">
</p>




## 📦 License

This project is licensed under the MIT License — feel free to use, modify, and share.

