import sqlite3

DB_NAME = 'flycamp_framework.db'

def clear_all_but_rfidtokens():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    tables_to_clear = ["PlayerRegistrations", "GamePlays", "PlayerBests", "InteractionLog"]

    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table}")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            print(f"Cleared table: {table}")
        except sqlite3.OperationalError:
            print(f"[ ] Table '{table}' does not exist - skipping.")

    conn.commit()
    conn.close()
    print("\nAll data (except RFIDTokens) has been cleared.")

if __name__ == "__main__":
    clear_all_but_rfidtokens()
