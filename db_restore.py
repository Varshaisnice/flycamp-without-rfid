import os
import shutil
import glob
from datetime import datetime

# --- Configuration ---
DB_NAME = '/home/devesh/CONSOLE/nfctest/flycamp_project/flycamp_framework.db'
BACKUP_DIR = '/home/devesh/CONSOLE/nfctest/flycamp_project/db_backups'

def find_available_backups():
    """Finds all .sqlite backup files in the backup directory."""
    search_path = os.path.join(BACKUP_DIR, '*.sqlite')
    backup_files = glob.glob(search_path)
    
    # Sort files by modification time, newest first
    backup_files.sort(key=os.path.getmtime, reverse=True)
    
    return backup_files

def restore_database(backup_path: str, dest_path: str):
    """
    Restores the database by copying the backup file over the main DB file.
    """
    try:
        print(f"\nRestoring from '{os.path.basename(backup_path)}' to '{os.path.basename(dest_path)}'...")
        # shutil.copy2 is appropriate here as we are replacing a file that
        # should not be in active use.
        shutil.copy2(backup_path, dest_path)
        print("? Restore successful!")
    except Exception as e:
        print(f"? Error during restore: {e}")

def main():
    """
    Main function to guide the user through the restore process.
    """
    print("--- Database Restore Utility ---")
    
    available_backups = find_available_backups()
    
    if not available_backups:
        print("No backup files (.sqlite) found in the backup directory.")
        return

    print("Available backups (newest first):")
    for i, file_path in enumerate(available_backups):
        filename = os.path.basename(file_path)
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        print(f"  {i + 1}: {filename} (Last modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')})")

    try:
        choice = int(input("\nEnter the number of the backup to restore: "))
        if not (1 <= choice <= len(available_backups)):
            print("Invalid choice.")
            return
        
        chosen_backup = available_backups[choice - 1]

    except (ValueError, IndexError):
        print("Invalid input. Please enter a number from the list.")
        return

    print("\n" + "="*40)
    print("??  WARNING!  ??")
    print("="*40)
    print(f"You are about to OVERWRITE the main database:")
    print(f"  '{DB_NAME}'")
    print(f"with the contents of the backup file:")
    print(f"  '{os.path.basename(chosen_backup)}'")
    print("\nThis action cannot be undone.")
    print("Please ensure no other applications are connected to the database.")
    
    confirm = input("\nAre you absolutely sure you want to continue? (yes/no): ")
    
    if confirm.lower() == 'yes':
        restore_database(chosen_backup, DB_NAME)
    else:
        print("Restore operation cancelled.")

if __name__ == "__main__":
    main()
