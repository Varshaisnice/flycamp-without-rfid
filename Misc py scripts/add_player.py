import sqlite3
import random
from datetime import datetime

# Connect to the database
conn = sqlite3.connect('games_data.db')
cursor = conn.cursor()

def get_next_serial():
    cursor.execute("SELECT MAX(sl_no) FROM Players")
    result = cursor.fetchone()
    return (result[0] or 0) + 1

def add_player():
    name = input("Enter player name: ").strip()

    while True:
        try:
            game_number = int(input("Choose Game (1 or 2): ").strip())
            if game_number in (1, 2):
                break
            else:
                print("Please enter 1 or 2.")
        except ValueError:
            print("Invalid input. Enter a number.")

    sl_no = get_next_serial()
    rfid_token = str(sl_no)
    play_zone = random.randint(1, 4)

    # Insert into Players
    cursor.execute("""
        INSERT INTO Players (sl_no, name, rfid_token, play_zone)
        VALUES (?, ?, ?, ?)
    """, (sl_no, name, rfid_token, play_zone))

    # Get the new player's ID
    player_id = cursor.lastrowid

    # Insert into Games table with default level and score
    cursor.execute("""
        INSERT INTO Games (player_id, game_number, level_number, score, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (player_id, game_number, 1, 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()

if __name__ == "__main__":
    add_player()
    conn.close()
