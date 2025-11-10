import sqlite3

DB_NAME = 'flycamp_framework.db'

def get_next_rfid_token(cursor):
    cursor.execute("SELECT MAX(CAST(token_id AS INTEGER)) FROM PlayerRegistrations")
    result = cursor.fetchone()
    return (result[0] or 0) + 1

def register_player():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    name = input("Enter your name: ").strip()

    # Check if player already exists
    cursor.execute("SELECT token_id FROM PlayerRegistrations WHERE player_name = ?", (name,))
    existing = cursor.fetchone()

    if existing:
        print(f"Player '{name}' is already registered with RFID Token: {existing[0]}")
    else:
        rfid_token = str(get_next_rfid_token(cursor))

        cursor.execute("""
            INSERT INTO PlayerRegistrations (player_name, token_id, play_zone)
            VALUES (?, ?)
        """, (name, rfid_token))

        conn.commit()
        print(f"Registered '{name}' with RFID Token: {rfid_token}")

    conn.close()

if __name__ == "__main__":
    register_player()
