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


# ---------------------- Formatting helpers ----------------------
class Formatters:
    @staticmethod
    def format_number(value: int, width: int) -> str:
        return str(value).zfill(width)

    @staticmethod
    def format_amount(value: int, width: int) -> str:
        return str(value).zfill(width)


# ---------------------- Transaction analysis ----------------------
class TransactionAnalyzer:
    def __init__(self, code_service):
        self.codes = code_service.transaction_codes
        self.code_service = code_service

    def calculate_totals_and_hash(
        self,
        transactions: List[Tuple[str, Any, str]],
        table_prefix: str,
        bank_code: str,
        branch_code: Optional[str] = None,
    ):
        credit_values = []
        debit_values = []
        hash_total = 0
        unknown_codes = set()

        for transaction_code, amount, dest_account in transactions:
            # Skip zero amounts ('0' or '000000000000')
            if amount in ["0", "000000000000"]:
                continue
            # Normalize amount to int
            try:
                if amount is None:
                    amount_int = 0
                elif isinstance(amount, str):
                    amount_int = int(amount.strip()) if amount.strip() else 0
                elif isinstance(amount, int):
                    amount_int = amount
                elif isinstance(amount, float):
                    amount_int = int(amount)
                else:
                    amount_int = 0
            except (ValueError, TypeError):
                amount_int = 0

            # Hash total from numeric part of destination account
            try:
                if dest_account and isinstance(dest_account, str):
                    account_numeric = "".join(filter(str.isdigit, dest_account))
                    if account_numeric:
                        hash_total += int(account_numeric)
            except (ValueError, TypeError):
                pass

            code_str = str(transaction_code).strip() if transaction_code else ""
            if code_str in self.codes:
                tx_type = self.codes[code_str].get("type", "").upper()
                if tx_type == "C":
                    credit_values.append(amount_int)
                elif tx_type == "D":
                    debit_values.append(amount_int)
            else:
                if code_str:
                    unknown_codes.add(code_str)

        # Unknown transaction code handling (prompt + DB update + refetch)
        if unknown_codes:
            print("" + "=" * 60)
            print("ERROR: Unknown transaction codes found:")
            for code in sorted(unknown_codes):
                print(f"  - Transaction Code: '{code}'")
            print("Available mappings from transaction_codes_mapping.json:")
            mapping = self.code_service._load_transaction_code_mappings()
            applicable = []
            for _, m in mapping.items():
                old_code = str(m.get("old", ""))
                new_code = str(m.get("new", ""))
                if old_code in unknown_codes:
                    applicable.append((old_code, new_code))
            
            if applicable:
                for old_code, new_code in applicable:
                    print(f"  - '{old_code}' -> '{new_code}'")
                print("Do you want to update the database with these mappings?")
                print(
                    "This will update transaction codes in the database according to the mapping file."
                )
                choice = (
                    input("Enter 'yes' to update and continue, or 'no' to abort: ")
                    .strip()
                    .lower()
                )
                if choice in ["yes", "y"]:
                    success = self.code_service.update_transaction_codes_in_database(
                        unknown_codes, table_prefix
                    )
                    if success:
                        # For SQLite, we need to close connections to avoid locking
                        # Database.reset_pooling()  # Remove or adjust if using SQLite
                        sleep_time.sleep(2)  # Shorter delay for SQLite
                        
                        if branch_code:
                            conn = Database.get_connection()
                            if conn:
                                cursor = conn.cursor()
                                branch_field = (
                                    "Originating_Branch_No"
                                    if table_prefix == "OUT"
                                    else "Destination_Branch_No"
                                )
                                q = f"""
                                    SELECT Transaction_Code, Amount, Destination_Ac_No
                                    FROM {table_prefix}_Transaction
                                    WHERE {branch_field} = ?
                                """
                                cursor.execute(q, (branch_code,))
                                updated = cursor.fetchall()
                                conn.close()

                                # RETURN SPECIAL SIGNAL TO CALLER
                                return ("REFETCH_NEEDED", updated)
                            else:
                                print(
                                    "Failed to establish new database connection for refetching"
                                )
                                sys.exit(1)
                        else:
                            print(
                                "No branch code available for refetching. Continuing with current data."
                            )
                            # Even without branch code, signal that refetch is needed
                            return ("REFETCH_NEEDED", [])
                    else:
                        print("Failed to update database. Aborting process.")
                        sys.exit(1)
                else:
                    print("Process aborted by user.")
                    sys.exit(1)
            else:
                print("No mappings found for the unknown transaction codes.")
                print(
                    "Please update the transaction_codes.json or transaction_codes_mapping.json file and try again."
                )
                sys.exit(1)

        credit_total = sum(credit_values)
        credit_count = len(credit_values)
        debit_total = sum(debit_values)
        debit_count = len(debit_values)
        return credit_total, credit_count, debit_total, debit_count, hash_total

