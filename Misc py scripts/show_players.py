import sqlite3

DB_NAME = 'flycamp_framework.db'

def show_players():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT rfid_token, name FROM Players ORDER BY player_id;")
    rows = cursor.fetchall()

    if not rows:
        print("No players found.")
    else:
        # Header
        print(f"{'Token':<10} | {'Name'}")
        print("-" * 30)

        # Rows
        for rfid, name in rows:
            print(f"{rfid:<10} | {name}")

    conn.close()

if __name__ == "__main__":
    show_players()
