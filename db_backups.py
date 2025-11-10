import os
import sqlite3
from datetime import datetime

# --- Configuration ---
# Using the full path you provided
DB_NAME = '/home/devesh/CONSOLE/nfctest/flycamp_project/flycamp_framework.db'
BACKUP_DIR = '/home/devesh/CONSOLE/nfctest/flycamp_project/db_backups'
FULL_BACKUP_PATH = os.path.join(BACKUP_DIR, 'backup_full.sqlite')
DELTA_TEMPLATE = os.path.join(BACKUP_DIR, 'backup_delta_{}.sqlite')

def safe_backup_db(source_db_path: str, dest_db_path: str):
    """
    Safely backs up a live SQLite database using the Online Backup API.
    (This function remains unchanged)
    """
    if not os.path.exists(source_db_path):
        print(f"[!] Error: Source database '{source_db_path}' not found.")
        return

    print(f"    -> Backing up '{os.path.basename(source_db_path)}' to '{os.path.basename(dest_db_path)}'...")
    
    try:
        source_conn = sqlite3.connect(source_db_path)
        backup_conn = sqlite3.connect(dest_db_path)

        with backup_conn:
            source_conn.backup(backup_conn, pages=1, progress=None)
        
        print(f"    -> Backup successful.")

    except sqlite3.Error as e:
        print(f"[!] Error during backup: {e}")
    finally:
        if 'source_conn' in locals():
            source_conn.close()
        if 'backup_conn' in locals():
            backup_conn.close()

def get_cycle_minute():
    """
    MODIFIED: Returns the current minute within a 5-minute cycle (0-4).
    """
    return datetime.now().minute % 5

def perform_backup():
    """
    MODIFIED: Performs a cyclical backup with a full backup on the 5th minute.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    minute_index = get_cycle_minute()

    # MODIFIED: Logic for a 5-minute cycle.
    # The cycle consists of minutes 0, 1, 2, 3, 4.
    # The full backup now runs on the last minute of the cycle (index 4).
    if minute_index == 4:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Minute 4 of cycle: Performing FULL backup.")
        safe_backup_db(DB_NAME, FULL_BACKUP_PATH)
    else:
        # For minutes 0, 1, 2, 3, this creates delta backups 1, 2, 3, 4.
        delta_index = minute_index + 1
        delta_file = DELTA_TEMPLATE.format(delta_index)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Minute {minute_index} of cycle: Writing to delta backup {delta_index}.")
        safe_backup_db(DB_NAME, delta_file)

if __name__ == "__main__":
    print("--- Starting Backup Check ---")
    perform_backup()
    print("--- Backup Check Complete ---")
