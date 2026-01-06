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


# ---------------------- Branch & Header services ----------------------
class BranchService:
    def __init__(self, analyzer, code_service):
        self.analyzer = analyzer
        self.code_service = code_service

    @staticmethod
    def _branch_field(table_prefix: str) -> str:
        return (
            "Originating_Branch_No"
            if table_prefix == "OUT"
            else "Destination_Branch_No"
        )

    def update_branch_status_and_totals(
        self, file_header_id: int, bank_code: str, table_prefix: str
    ) -> bool:
        max_retries = 3
        for retry in range(max_retries):
            result = self._process_branches_with_refetch(
                file_header_id, bank_code, table_prefix, retry
            )
            
            if result is True:
                return True
            elif result == "COMPLETE":
                return True
            elif result == "REFETCH_NEEDED":
                sleep_time.sleep(2)  # Wait for database updates to settle
                continue
            else:
                return False
        
        print(f"Max retries ({max_retries}) exceeded")
        return False

    def _process_branches_with_refetch(
        self, file_header_id: int, bank_code: str, table_prefix: str, attempt: int
    ):
        """Process branches with proper error handling and refetch support"""
        conn = Database.get_connection()
        if not conn:
            print("Failed to connect to database.")
            return False
            
        cursor = conn.cursor()
        
        try:
            # Fetch all pending branches
            cursor.execute(
                f"""
                SELECT Id, BranchCode
                FROM {table_prefix}_BranchHeader
                WHERE Status = 0 AND BankCode = ?
                ORDER BY Id
                """,
                (bank_code,)
            )
            pending = cursor.fetchall()

            if not pending:
                print("No pending branches.")
                return "COMPLETE"

            print(f"Found {len(pending)} branches to process")
            branch_field = self._branch_field(table_prefix)

            # Process each branch
            for branch_header_id, branch_code in pending:
                result = self._process_single_branch(
                    conn, cursor, branch_header_id, branch_code, 
                    bank_code, table_prefix, branch_field
                )
                
                if result == "REFETCH_NEEDED":
                    # Rollback any partial changes and signal refetch needed
                    conn.rollback()
                    return "REFETCH_NEEDED"
                elif not result:
                    # Error processing branch
                    conn.rollback()
                    return False
            
            # Commit all updates
            conn.commit()
            return "COMPLETE"
            
        except Exception as e:
            print(f"Error updating branch status: {e}")
            if conn:
                conn.rollback()
            return False
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _process_single_branch(
        self, main_conn, main_cursor, branch_header_id: int, branch_code: str,
        bank_code: str, table_prefix: str, branch_field: str
    ):
        """Process a single branch, returns True, "REFETCH_NEEDED", or False"""
        try:
            # Create new connection for this branch's transactions
            branch_conn = Database.get_connection()
            if not branch_conn:
                print(f"Failed to connect for branch {branch_code}")
                return False
                
            branch_cursor = branch_conn.cursor()
            
            try:
                # Fetch transactions for this branch
                branch_cursor.execute(
                    f"""
                    SELECT Transaction_Code, Amount, Destination_Ac_No
                    FROM {table_prefix}_Transaction
                    WHERE {branch_field} = ?
                    """,
                    (branch_code,)
                )
                transactions = branch_cursor.fetchall()
                
                if not transactions:
                    print(f"Branch {branch_code}: 0 transactions (status updated)")
                    # Update status only for empty branches
                    main_cursor.execute(
                        f"""
                        UPDATE {table_prefix}_BranchHeader
                        SET Status = 1
                        WHERE Id = ?
                        """,
                        (branch_header_id,)
                    )
                    return True
                    
                # Analyze transactions
                result = self.analyzer.calculate_totals_and_hash(
                    transactions, table_prefix, bank_code, branch_code
                )
                
                # Handle REFETCH_NEEDED scenario
                if isinstance(result, tuple) and result[0] == "REFETCH_NEEDED":
                    return "REFETCH_NEEDED"
                
                # Normal result - update branch totals
                credit_total, credit_count, debit_total, debit_count, hash_total = result
                
                main_cursor.execute(
                    f"""
                    UPDATE {table_prefix}_BranchHeader
                    SET CreditTotal = ?, NumCreditItems = ?,
                        DebitTotal = ?, NumDebitItems = ?,
                        AccountHashTotal = ?, Status = 1
                    WHERE Id = ?
                    """,
                    (
                        credit_total,
                        credit_count,
                        debit_total,
                        debit_count,
                        hash_total,
                        branch_header_id,
                    )
                )
                
                return True
                
            finally:
                # Always close branch connection
                if branch_cursor:
                    branch_cursor.close()
                if branch_conn:
                    branch_conn.close()
                    
        except Exception as e:
            print(f"Error processing branch {branch_code}: {e}")
            return False


class BranchInspector:
    @staticmethod
    def _branch_field(table_prefix: str) -> str:
        return (
            "Originating_Branch_No"
            if table_prefix == "OUT"
            else "Destination_Branch_No"
        )

    def check_and_filter(
        self, bank_code: str, table_prefix: str
    ) -> Tuple[bool, List[str], List[Any]]:
        conn = Database.get_connection()
        cursor = conn.cursor()
        try:
            branch_headers_query = f"""
                SELECT bh.Id, bh.BranchControlId, bh.FieldId, bh.FileDate, bh.BankCode,
                       bh.BranchCode, bh.CreditTotal, bh.NumCreditItems, bh.DebitTotal,
                       bh.NumDebitItems, bh.AccountHashTotal, bh.Status, bh.FileName
                FROM {table_prefix}_BranchHeader bh
                WHERE bh.BankCode = ?
                ORDER BY bh.Id
            """
            cursor.execute(branch_headers_query, (bank_code,))
            branch_headers = cursor.fetchall()
            if not branch_headers:
                return False, [], []
            problems: List[str] = []
            filtered: List[Any] = []
            branch_field = self._branch_field(table_prefix)

            for bh in branch_headers:
                branch_code = bh[5]
                count_query = f"""
                    SELECT COUNT(*)
                    FROM {table_prefix}_Transaction
                    WHERE {branch_field} = ?
                """
                cursor.execute(count_query, (branch_code,))
                total_count = cursor.fetchone()[0]

                non_zero_query = f"""
                    SELECT COUNT(*)
                    FROM {table_prefix}_Transaction
                    WHERE {branch_field} = ?
                      AND Amount NOT IN ('0', '000000000000')
                      AND Amount IS NOT NULL
                      AND Amount != ''
                """
                cursor.execute(non_zero_query, (branch_code,))
                non_zero_count = cursor.fetchone()[0]

                if total_count == 0:
                    problems.append(f"Branch {branch_code} has 0 transactions")
                elif non_zero_count == 0:
                    problems.append(
                        f"Branch {branch_code} has only zero-amount transactions ('0' or '000000000000')"
                    )
                elif total_count == 1 and non_zero_count == 0:
                    problems.append(
                        f"Branch {branch_code} has only 1 transaction with amount '0' or '000000000000'"
                    )
                else:
                    filtered.append(bh)
            return len(problems) > 0, problems, filtered
        except Exception as e:
            print(f"Error checking branch transactions: {e}")
            return True, [f"Error checking transactions: {e}"], []
        finally:
            conn.close()

