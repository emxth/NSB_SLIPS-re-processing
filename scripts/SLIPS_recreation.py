from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Optional, Tuple, List, Any
import time as sleep_time
import json
import sys
import sqlite3


# ---------------------- Settings & Configuration ----------------------
class Settings:
    BASE_PATH: Path = None
    CUTOFF_TIME = time(15, 0)  # 3 PM cutoff for next working date
    BANK_PW = "68771968"
    LANKA_CLEAR_PW = "10901939"

    # SQLite database path - should be in root directory
    @staticmethod
    def initialize_paths(base_path: Path):
        """Sets the absolute base path for the application."""
        Settings.BASE_PATH = base_path

    @staticmethod
    def get_db_path():
        if Settings.BASE_PATH is None:
            raise RuntimeError("Settings.BASE_PATH must be initialized via initialize_paths()")
        return Settings.BASE_PATH / "SLIPS.db"

    @staticmethod
    def path_config(filename: str) -> Path:
        if Settings.BASE_PATH is None:
            raise RuntimeError("Settings.BASE_PATH must be initialized via initialize_paths()")
        return Settings.BASE_PATH / "config" / filename

    @staticmethod
    def load_json(path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: JSON file '{path}' not found.")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in '{path}': {e}")
            return {}


# ---------------------- Database Layer ----------------------
class Database:
    @staticmethod
    def get_connection():
        db_path = Path(Settings.get_db_path())

        try:
            # Timeout helps avoid "database locked" by giving time for other writes to finish.
            conn = sqlite3.connect(
                str(db_path),
                timeout=10,            # waits up to 10s before throwing "database locked"
                isolation_level=None,  # explicit transactions, no auto-commit locks
                check_same_thread=False  # safe for threads if you grow into that
            )

            # Enable WAL mode (best for concurrent reads + writes)
            conn.execute("PRAGMA journal_mode = WAL")

            # Foreign keys ON always recommended
            conn.execute("PRAGMA foreign_keys = ON")

            # Synchronous NORMAL = faster writes, still safe for WAL
            conn.execute("PRAGMA synchronous = NORMAL")

            return conn

        except Exception as e:
            print(f"[DB ERROR] Failed establishing DB connection: {e}")
            return None

    @staticmethod
    def close_safely(conn, cursor=None):
        """Utility helper to close cursor and connection safely."""
        try:
            if cursor:
                cursor.close()
        except:
            pass
        try:
            if conn:
                conn.close()
        except:
            pass


    @staticmethod
    def reset_pooling():
        """
        Dummy function if your app previously used pooling.
        Now pooling is unnecessary with SQLite + WAL,
        but you may keep this for backward-compatibility.
        """
        pass


# ---------------------- Transaction codes & mapping ----------------------
class CodeMappingService:
    def __init__(self):
        self.transaction_codes = self._load_transaction_codes()
        self.mappings = self._load_transaction_code_mappings()

    def _load_transaction_codes(self) -> dict:
        path = Settings.path_config("transaction_codes.json")
        try:
            return Settings.load_json(path)
        except FileNotFoundError:
            print(f"Error: Transaction codes file '{path}' not found.")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in transaction codes file: {e}")
            return {}

    def _load_transaction_code_mappings(self) -> dict:
        path = Settings.path_config("transaction_codes_mapping.json")
        try:
            return Settings.load_json(path)
        except FileNotFoundError:
            print(f"Warning: Transaction codes mapping file '{path}' not found.")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in transaction codes mapping file: {e}")
            return {}

    def refresh_mappings(self):
        self.mappings = self._load_transaction_code_mappings()

    def update_transaction_codes_in_database(
        self, unknown_codes: set, table_prefix: str
    ) -> bool:
        mapping = self._load_transaction_code_mappings()
        if not mapping:
            print("No transaction code mappings found. Cannot update database.")
            return False
            
        conn = Database.get_connection()
        if not conn:
            print("Failed to connect to database for updating transaction codes.")
            return False
            
        cursor = conn.cursor()
        
        try:
            # For SQLite, use immediate transaction to avoid locking issues
            cursor.execute("BEGIN IMMEDIATE")
            
            updates_made = 0
            print("Updating transaction codes in database...")
            
            for _, mapping_data in mapping.items():
                old_code = str(mapping_data.get("old", ""))
                new_code = str(mapping_data.get("new", ""))
                
                if old_code and new_code and old_code in unknown_codes:
                    cursor.execute(
                        f"""
                        UPDATE {table_prefix}_Transaction
                        SET Transaction_Code = ?
                        WHERE Transaction_Code = ?
                        """,
                        (new_code, old_code)
                    )
                    rows_affected = cursor.rowcount
                    updates_made += rows_affected
                    print(
                        f"  - Updated {rows_affected} transactions: '{old_code}' -> '{new_code}'"
                    )
            
            conn.commit()
            print(f"Successfully updated {updates_made} transactions in database.")
            return True
            
        except Exception as e:
            print(f"Error updating transaction codes in database: {e}")
            conn.rollback()
            return False
            
        finally:
            cursor.close()
            conn.close()

