import sqlite3
from pathlib import Path


def initialize_database():
    """Initialize SQLite database with schema in root directory"""

    script_dir = Path(__file__).parent
    root_dir = script_dir.parent  # Go up one level to root

    db_path = root_dir / "SLIPS.db"
    schema_file = script_dir / "SLIPS-database-creation.sql"

    print(f"Script directory: {script_dir}")
    print(f"Root directory: {root_dir}")
    print(f"Database will be created at: {db_path}")
    print(f"Using schema file: {schema_file}")

    # Check if schema file exists
    if not schema_file.exists():
        print(f"ERROR: Schema file not found at {schema_file}")
        return

    # Read the SQL schema
    with open(schema_file, "r") as f:
        schema_sql = f.read()

    # Connect to SQLite database (creates if doesn't exist)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Execute the schema SQL
    cursor.executescript(schema_sql)

    # Verify tables were created
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("\nTables created:")
    for table in tables:
        print(f"  - {table[0]}")

    conn.commit()
    conn.close()
    print(f"\nDatabase initialized: {db_path}")


if __name__ == "__main__":
    initialize_database()
