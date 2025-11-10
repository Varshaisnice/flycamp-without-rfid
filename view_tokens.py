import sqlite3

DB_NAME = 'flycamp_framework.db'

def show_tokens():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT rfid_uid, token_id FROM RFIDTokens ORDER BY token_id;")
    rows = cursor.fetchall()

    if not rows:
        print("No RFID tokens registered.")
    else:
        print(f"{'UID':<20} | {'Token ID'}")
        print("-" * 35)
        for uid, token_id in rows:
            print(f"{uid:<20} | {token_id}")

    conn.close()

if __name__ == "__main__":
    show_tokens()
