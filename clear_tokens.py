import sqlite3

DB_NAME = 'flycamp_framework.db'

def clear_rfid_tokens():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Delete all rows
    cursor.execute("DELETE FROM RFIDTokens")

    # Reset autoincrement counter
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='RFIDTokens'")

    conn.commit()
    conn.close()
    print("RFIDTokens table cleared and token IDs reset.")

if __name__ == "__main__":
    clear_rfid_tokens()
