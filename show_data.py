import sqlite3

# Connect to the database
DB_NAME = 'flycamp_framework.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

def print_rows(title, headers, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("No data.")
        return

    col_widths = [max(len(str(item)) for item in col) for col in zip(*([headers] + rows))]
    fmt = " | ".join("{:<" + str(width) + "}" for width in col_widths)

    print(fmt.format(*headers))
    print("-" * (sum(col_widths) + 3 * (len(headers) - 1)))
    for row in rows:
        print(fmt.format(*row))

def show_table_data():
    # 1. Players
    cursor.execute("SELECT sl_no, name, rfid_token, play_zone FROM Players ORDER BY sl_no")
    print_rows("Players", ["sl_no", "name", "rfid_token", "play_zone"], cursor.fetchall())

    # 2. OverallStats
    cursor.execute("SELECT rfid_token, overall_play_count, overall_score FROM OverallStats")
    print_rows("OverallStats", ["rfid_token", "overall_play_count", "overall_score"], cursor.fetchall())

    # 3. RFIDTokens
    cursor.execute("SELECT token_id, uid FROM RFIDTokens ORDER BY token_id")
    print_rows("RFIDTokens", ["token_id", "uid"], cursor.fetchall())

    # 4. GameSessions
    cursor.execute("SELECT session_id, rfid_token, game_number, level_number, timestamp FROM GameSessions ORDER BY session_id")
    print_rows("GameSessions", ["session_id", "rfid_token", "game_number", "level_number", "timestamp"], cursor.fetchall())

    # 5. PlayerStats
    cursor.execute("SELECT rfid_token, game_number, level_number, play_count, score_total FROM PlayerStats")
    print_rows("PlayerStats", ["rfid_token", "game_number", "level_number", "play_count", "score_total"], cursor.fetchall())

    # 6. sqlite_sequence (optional)
    cursor.execute("SELECT name, seq FROM sqlite_sequence")
    print_rows("sqlite_sequence", ["name", "seq"], cursor.fetchall())

if __name__ == "__main__":
    show_table_data()
    conn.close()
