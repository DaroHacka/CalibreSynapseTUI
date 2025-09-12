#!/bin/bash

# === CONFIGURATION ===
# Replace this with the path to your Calibre Library
CALIBRE_LIB="/srv/dev-disk-by-uuid-2856cdb9-5991-47dc-886b-1be20f8c2993/ArkVault/Calibre Library"

# Log directory and file
LOG_DIR="$HOME/.local/share/calibre_import"
LOG_FILE="$LOG_DIR/calibre_import.log"

# === PREPARE LOG DIRECTORY ===
mkdir -p "$LOG_DIR"

# === START LOG ===
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Calibre Import Started ===" >> "$LOG_FILE"

# === USER PROMPT ===
echo "Do you want to import a single file or multiple files? (Type: single / multi)"
read -r MODE

if [[ "$MODE" == "single" ]]; then
    echo "Paste the full path to the file you want to import:"
    read -r FILE_PATH
    FILE_PATH=$(echo "$FILE_PATH" | sed -e 's/^"//' -e 's/"$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    if [[ -f "$FILE_PATH" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding single file: $FILE_PATH" >> "$LOG_FILE"
        calibredb add "$FILE_PATH" --with-library "$CALIBRE_LIB" >> "$LOG_FILE" 2>&1
        echo "✅ File imported successfully."
    else
        echo "❌ Error: File not found at $FILE_PATH"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: File not found at $FILE_PATH" >> "$LOG_FILE"
    fi

elif [[ "$MODE" == "multi" ]]; then
    echo "Paste the full path to the folder containing the files:"
    read -r FOLDER_PATH
    FOLDER_PATH=$(echo "$FOLDER_PATH" | sed -e 's/^"//' -e 's/"$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    if [[ -d "$FOLDER_PATH" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scanning folder: $FOLDER_PATH" >> "$LOG_FILE"
        find "$FOLDER_PATH" -type f \( \
            -iname "*.epub" -o -iname "*.pdf" -o -iname "*.cbz" -o -iname "*.cbr" -o \
            -iname "*.mobi" -o -iname "*.azw" -o -iname "*.azw3" -o -iname "*.txt" -o \
            -iname "*.djvu" -o -iname "*.lit" -o -iname "*.fb2" -o -iname "*.zip" -o \
            -iname "*.rar" \
        \) | while read -r FILE; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding: $FILE" >> "$LOG_FILE"
            calibredb add "$FILE" --with-library "$CALIBRE_LIB" >> "$LOG_FILE" 2>&1
        done
        echo "✅ All files imported successfully."
    else
        echo "❌ Error: Folder not found at $FOLDER_PATH"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Folder not found at $FOLDER_PATH" >> "$LOG_FILE"
    fi

else
    echo "❌ Invalid input. Please type 'single' or 'multi'."
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Invalid mode selected: $MODE" >> "$LOG_FILE"
fi

# === FIX PERMISSIONS AFTER IMPORT ===
chown -R "$USER:users" "$CALIBRE_LIB"
chmod -R ug+rwX,o-w "$CALIBRE_LIB"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Calibre Import Finished ===" >> "$LOG_FILE"
