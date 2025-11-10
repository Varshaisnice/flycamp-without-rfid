import sqlite3

DB_NAME = 'flycamp_framework.db'

def inspect_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    print("\n=== Tables in Database ===")
    for table in tables:
        print(f"\n{table}")
        # Show columns
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        for col in columns:
            cid, name, dtype, notnull, default, pk = col
            print(f"  - {name} ({dtype}){' [PK]' if pk else ''}")
        # Optional: Show row count
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  Rows: {count}")

    conn.close()

if __name__ == "__main__":
    inspect_database()
