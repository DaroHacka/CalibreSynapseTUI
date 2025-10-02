label_disambiguator.py — Why You’ll Eventually Need It

At first, you won’t. When you’re starting out with just a few dozen labels across Calibre columns, everything feels clean. But once you hit 300, 500, or more AI-generated labels, things start to break, well not necessarily.

The premise is simple: over time, AI tends to generate **similar labels across different categories**. And Calibre merges them globally, which causes confusion, filtering bugs, and even label omission.

---

## ❓ The Problem

Let’s say you have these categories (Calibre columns):

- `emotional_tone`
- `writing_style`
- `book_setting`

And AI generates the label `"episodic"` for all three. Calibre treats them as one global label. So when you filter by `"episodic"` in `writing_style`, you might accidentally include books where `"episodic"` was meant as a **setting** or **tone** — or worse, the label disappears entirely due to conflict.

This happens with tons of expressive labels:

| Label      | Category A           | Category B           |
|------------|----------------------|----------------------|
| `episodic` | writing_style        | book_setting         |
| `irreverent` | emotional_tone     | subgenre             |
| `campy`    | emotional_tone        | genre                |
| `dark`     | emotional_tone        | book_setting         |
| `satirical`| writing_style         | subgenre             |

---

## 🛠️ What the Script Does

`label_disambiguator.py` solves this by:

1. **Loading your semantic label map** — a dictionary like:
   ```python
   {
     "book123": {
       "emotional_tone": ["dark", "campy"],
       "writing_style": ["episodic", "satirical"]
     },
     ...
   }
   ```

2. **Scanning all books** to detect labels that appear in multiple categories.

3. **Renaming duplicates** by appending a suffix based on the category:
   - `"episodic"` in `writing_style` → `"episodic-ws"`
   - `"episodic"` in `book_setting` → `"episodic-bs"`
   - `"campy"` in `emotional_tone` → `"campy-et"`
   - `"campy"` in `genre` → `"campy-g"`

4. **Pushing updated labels** to Calibre Server via its API.

5. **Running `Semantic_Compatibility_Matrix_Builder.py`** to rebuild the matrix and restore filtering logic.

---

## 🎨 UI Elegance: Hiding the Suffixes

To keep the TUI clean, I added this:

```python
def strip_suffix(self, label):
    return re.sub(r"-(et|ws|bs|sg|g|p|t|s|pv|pc|rl|rm|pp|a|ct|ns|mv|mg|l)$", "", label)
```

This strips suffixes from the UI display, so `"episodic-ws"` shows as `"episodic"` — but the suffix still exists internally for filtering and conflict resolution.

---

## 📚 Full List of Suffixes and Their Meanings

| Suffix | Category (Calibre Column)         |
|--------|-----------------------------------|
| `et`   | emotional_tone                    |
| `ws`   | writing_style                     |
| `bs`   | book_setting                      |
| `sg`   | subgenre                          |
| `g`    | genre                             |
| `p`    | pacing                            |
| `t`    | theme                             |
| `s`    | structure                         |
| `pv`   | plot_vector                       |
| `pc`   | protagonist_character             |
| `rl`   | relationship_layer                |
| `rm`   | romantic_mood                     |
| `pp`   | publication_period                |
| `a`    | audience                          |
| `ct`   | cultural_tone                     |
| `ns`   | narrative_scope                   |
| `mv`   | moral_vector                      |
| `mg`   | mythological_grade                |
| `l`    | language                          |

You can use whatever suffixes you want — these are just mine and mirrors the columns I created in my Calibre Library. The key is consistency.

---

## 🧩 Why This Matters

You could ask AI to suffix labels per category during generation — but that’s fragile and hard to track. I prefer letting AI fill the blanks freely, then curating labels afterward with this script.

It’s not the only solution, but for large archives, it’s the only scalable one I’ve found. Otherwise, you’d have to manually track every label across every category — and that’s not practical when AI is generating dozens per entry.

This script lets you curate after the fact, with clarity and control.

