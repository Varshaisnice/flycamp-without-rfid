import sqlite3
import time

DB_NAME = 'flycamp_framework.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS RFIDTokens (
            token_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_uid TEXT UNIQUE NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def register_uid(uid):
    uid = uid.strip().upper()
    if not uid:
        print("[!] Empty UID. Try again.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT token_id FROM RFIDTokens WHERE rfid_uid = ?", (uid,))
    existing = cursor.fetchone()
    if existing:
        print(f"[!] UID {uid} is already registered with Token ID: {existing[0]}")
    else:
        cursor.execute("INSERT INTO RFIDTokens (rfid_uid) VALUES (?)", (uid,))
        conn.commit()
        token_id = cursor.lastrowid
        print(f"[+] UID {uid} registered with new Token ID: {token_id}")
    conn.close()

def main():
    init_db()
    print("FlyCamp Framework - Manual RFID Registration (No Hardware)")
    print("Enter UID in hex format (e.g., 04A1B2C3) or 'list' to view, 'quit' to exit.\n")

    while True:
        user_input = input("Enter UID > ").strip()

        if user_input.lower() == 'quit':
            print("Goodbye!")
            break
        elif user_input.lower() == 'list':
            show_tokens()
            continue
        elif len(user_input.replace(" ", "")) < 4:
            print("[!] UID too short. Minimum 4 chars (e.g., 04A1).")
            continue

        # Clean input: remove spaces, make uppercase
        clean_uid = user_input.replace(" ", "").upper()
        print(f"\n[+] Simulating tag detection: {clean_uid}")
        register_uid(clean_uid)
        print()

def show_tokens():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT rfid_uid, token_id FROM RFIDTokens ORDER BY token_id;")
    rows = cursor.fetchall()
    if not rows:
        print("No RFID tokens registered yet.")
    else:
        print(f"\n{'UID':<20} | {'Token ID'}")
        print("-" * 35)
        for uid, token_id in rows:
            print(f"{uid:<20} | {token_id}")
    conn.close()

if __name__ == "__main__":
    main()