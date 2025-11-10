#!/usr/bin/env python3
# get_id.py - MOCK VERSION (NO NFC READER NEEDED)
# Reads rfid_token.txt written by Flask UI

import os
import sys
import time

# === CONFIG: Update this path to match your app.py ===
TOKEN_FILE = 'rfid_token.txt'  # Same folder as app.py
DB_NAME = 'flycamp_framework.db'

# Optional: fallback to full path if needed
# TOKEN_FILE = '/home/devesh/Console/fly_camp_console/rfid_token.txt'

def read_token_from_file():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            content = f.read().strip()
            return int(content) if content.isdigit() else None
    except Exception as e:
        print(f"Error reading token file: {e}", file=sys.stderr)
        return None

def main():
    print("Waiting for token in rfid_token.txt...", file=sys.stderr)
    
    while True:
        token_id = read_token_from_file()
        if token_id is not None:
            print(f"Token ID: {token_id}")
            sys.stdout.flush()
            break
        time.sleep(0.5)

if __name__ == "__main__":
    main()