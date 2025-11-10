python -c "
import sqlite3
db = 'flycamp_framework.db'
conn = sqlite3.connect(db)
c = conn.cursor()

# Create tables
c.execute('''CREATE TABLE IF NOT EXISTS RFIDTokens
             (token_id INTEGER PRIMARY KEY AUTOINCREMENT, rfid_uid TEXT UNIQUE NOT NULL)''')
c.execute('''CREATE TABLE IF NOT EXISTS PlayerRegistrations
             (registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
              token_id INTEGER UNIQUE NOT NULL,
              player_name TEXT NOT NULL,
              FOREIGN KEY(token_id) REFERENCES RFIDTokens(token_id))''')
c.execute('''CREATE TABLE IF NOT EXISTS GamePlays
             (play_id INTEGER PRIMARY KEY AUTOINCREMENT,
              token_id INTEGER NOT NULL, game_number INTEGER, level_number INTEGER,
              score INTEGER, begin_timestamp INTEGER, end_timestamp INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS PlayerBests
             (player_best_id INTEGER PRIMARY KEY AUTOINCREMENT,
              token_id INTEGER NOT NULL, game_number INTEGER, level_number INTEGER,
              highest_score INTEGER, timestamp_achieved INTEGER,
              UNIQUE(token_id, game_number, level_number))''')

# Insert test data
c.execute(\"INSERT OR IGNORE INTO RFIDTokens (rfid_uid) VALUES ('TEST0001')")
c.execute(\"INSERT OR IGNORE INTO PlayerRegistrations (token_id, player_name) VALUES (1, 'Varsha')")

conn.commit()
conn.close()
print('Database created: flycamp_framework.db')
print('Test token: 1 (Name: Varsha)')
"