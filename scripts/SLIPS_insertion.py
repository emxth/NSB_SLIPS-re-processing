import sqlite3
import json
from pathlib import Path


class ConfigLoader:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.transaction_codes = self.load_transaction_codes()

    def load_transaction_codes(self):
        json_file_path = self.config_dir / "transaction_codes.json"
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            # Enable foreign keys and better text handling
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA encoding = 'UTF-8'")
            return self.conn.cursor()

        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def clear_tables(self, cursor, prefix):
        valid_prefixes = ["INW", "OUT"]

        if prefix not in valid_prefixes:
            raise ValueError(f"Invalid prefix: {prefix}")

        for table in [
            f"{prefix}_FileHeader",
            f"{prefix}_BranchHeader",
            f"{prefix}_Transaction",
        ]:
            cursor.execute(f"DELETE FROM {table}")

    def commit_and_close(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()

