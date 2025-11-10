import sqlite3

# The name of your database file
DB_FILE = 'flycamp_framework.db'

# SQL script to drop all old tables and create the new, efficient schema
# Using IF EXISTS prevents errors if the tables are already gone.
# Using executescript allows running multiple SQL statements at once.
reset_schema_sql = """
-- ========= DROPPING OLD TABLES =========
DROP TABLE IF EXISTS Players;
DROP TABLE IF EXISTS RFIDTokens; -- Dropping in case it exists from a previous attempt
DROP TABLE IF EXISTS GameSessions;
DROP TABLE IF EXISTS PlayerStats;
DROP TABLE IF EXISTS OverallStats;
DROP TABLE IF EXISTS PendingGameSession;
DROP TABLE IF EXISTS GamePlays; -- Also dropping new tables in case of re-run
DROP TABLE IF EXISTS PlayerRegistrations;
DROP TABLE IF EXISTS PlayerBests;
DROP TABLE IF EXISTS InteractionLog;


-- ========= CREATING NEW, EFFICIENT SCHEMA =========

-- Table 1: Master inventory of all physical RFID tokens you own.
CREATE TABLE RFIDTokens (
    token_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    rfid_uid    TEXT NOT NULL UNIQUE
);

-- Table 2: Links a token to a player for the duration of an event.
CREATE TABLE PlayerRegistrations (
    registration_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id                  INTEGER NOT NULL UNIQUE,
    player_name               TEXT NOT NULL,
    registration_timestamp    INTEGER NOT NULL,
    FOREIGN KEY(token_id) REFERENCES RFIDTokens(token_id) ON DELETE CASCADE
);

-- Table 3: The complete historical log of every single game played.
CREATE TABLE GamePlays (
    play_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id            INTEGER NOT NULL,
    game_number         INTEGER NOT NULL,
    level_number        INTEGER NOT NULL,
    score               INTEGER NOT NULL,
    begin_timestamp     INTEGER NOT NULL,
    end_timestamp       INTEGER NOT NULL,
    FOREIGN KEY(token_id) REFERENCES RFIDTokens(token_id) ON DELETE CASCADE
);

-- Table 4: A performance-enhancing summary table for personal bests.
CREATE TABLE PlayerBests (
    player_best_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id            INTEGER NOT NULL,
    game_number         INTEGER NOT NULL,
    level_number        INTEGER NOT NULL,
    highest_score       INTEGER NOT NULL,
    timestamp_achieved  INTEGER NOT NULL,
    FOREIGN KEY(token_id) REFERENCES RFIDTokens(token_id) ON DELETE CASCADE,
    UNIQUE(token_id, game_number, level_number)
);

-- Table 5: A simple, raw log of every single tap for debugging purposes.
CREATE TABLE InteractionLog (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfid_uid            TEXT NOT NULL,
    interaction_type    TEXT NOT NULL,
    timestamp           INTEGER NOT NULL
);


-- ========= CREATING INDEXES FOR PERFORMANCE =========

-- Speeds up finding all plays for a specific player.
CREATE INDEX idx_gameplays_token_id ON GamePlays(token_id);

-- Speeds up finding the top scores for a specific game/level (leaderboards).
CREATE INDEX idx_playerbests_leaderboard ON PlayerBests(game_number, level_number, highest_score DESC);

"""

def reset_database():
    """Connects to the database, drops old tables, and creates the new schema."""
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        print(f"Successfully connected to {DB_FILE}")

        # Execute the entire script to reset the schema
        cursor.executescript(reset_schema_sql)
        print("Dropping old tables...")
        print("Creating new schema...")

        # Commit the changes and close the connection
        conn.commit()
        print("Schema reset successful. All changes have been saved.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    # WARNING and confirmation
    print("⚠️ WARNING: This script will completely reset the schema of your database.")
    print(f"All existing tables in '{DB_FILE}' will be dropped and replaced.")
    print("Please ensure you have a backup of your database file.")
    
    confirm = input("Are you sure you want to continue? (yes/no): ")
    
    if confirm.lower() == 'yes':
        reset_database()
    else:
        print("Operation cancelled.")
