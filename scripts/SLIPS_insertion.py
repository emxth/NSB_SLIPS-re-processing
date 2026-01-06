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


class RecordParser:
    def __init__(self, transaction_codes):
        self.transaction_codes = transaction_codes

    def parse_header1(self, line, file_name):
        return {
            "BankControlId": line[0:4],
            "FieldId": line[4:7],
            "Date": line[7:12],
            "BankCode": line[12:16],
            "NoOfBatches": line[16:19],
            "NoOfTransactions": line[19:25],
            "FileName": file_name,
        }

    def parse_header2(self, line, file_name):
        return {
            "BranchControlId": line[0:4],
            "FieldId": line[4:7],
            "Date": line[7:12],
            "BankCode": line[12:16],
            "BranchCode": line[16:19],
            "CreditTotal": line[19:34],
            "NoOfCreditItems": line[34:40],
            "DebitTotal": line[40:55],
            "NoOfDebitItems": line[55:61],
            "HashTotal": line[61:79],
            "FileName": file_name,
        }

    def parse_data_record(self, line, file_name):
        code = line[43:45]
        desc = self.transaction_codes.get(code, {}).get("desc", "Unknown")
        return {
            "TransactionId": line[0:4],
            "DestBank": line[4:8],
            "DestBranch": line[8:11],
            "DestAccount": line[11:23],
            "DestName": line[23:43],
            "ReturnCode": line[45:47],
            "Filler": line[47:48],
            "ReturnDate": line[48:54],
            "TransactionCode": code,
            "TransactionDesc": desc,
            "Amount": line[54:66],
            "Currency": line[66:69],
            "OriginatingBankNo": line[69:73],
            "OriginatingBranchNo": line[73:76],
            "OriginatingAccountNo": line[76:88],
            "OriginatorAccountName": line[88:108],
            "Particular": line[108:123],
            "Reference": line[123:138],
            "ValueDate": line[138:144],
            "SecurityCheck": line[144:150],
            "FileName": file_name,
            "AmountInt": line[54:66].strip(),
        }

    def parse_dataset(self, dataset, file_name):
        parsed_groups = []
        first_5555 = dataset.find("5555")

        if first_5555 == -1:
            return parsed_groups

        if first_5555 + 180 <= len(dataset):
            header1_line = dataset[first_5555 : first_5555 + 180]
            header1 = self.parse_header1(header1_line, file_name)
            branch_data = self.find_branch_data(dataset, first_5555 + 180, file_name)
            parsed_groups.append(
                {
                    "type": header1["FieldId"],
                    "header1": header1,
                    "branches": branch_data,
                }
            )
        return parsed_groups

    def find_branch_data(self, dataset, start_pos, file_name):
        branches = []
        pos = start_pos

        while pos < len(dataset):
            next_4444 = dataset.find("4444", pos)
            if next_4444 == -1:
                break

            next_5555 = dataset.find("5555", pos)
            if next_5555 != -1 and next_5555 < next_4444:
                break

            if next_4444 + 180 <= len(dataset):
                header2_line = dataset[next_4444 : next_4444 + 180]
                header2 = self.parse_header2(header2_line, file_name)
                transaction_start = next_4444 + 180
                transactions = self.find_transactions(
                    dataset, transaction_start, file_name
                )
                branches.append({"header2": header2, "data": transactions})
                pos = transaction_start + (len(transactions) * 180)
            else:
                break

        return branches

    def find_transactions(self, dataset, start_pos, file_name):
        transactions = []
        pos = start_pos

        while pos + 180 <= len(dataset):
            if dataset[pos : pos + 4] == "0000":
                transaction_line = dataset[pos : pos + 180]
                transaction = self.parse_data_record(transaction_line, file_name)
                transactions.append(transaction)
                pos += 180
            else:
                break

        return transactions


class DataInserter:
    def __init__(self, db_manager, config_dir: Path):
        self.db_manager = db_manager
        self.config_dir = config_dir # Store the config_dir (which is base_path / "config")
        self.invalid_transactions = []
        self.current_file_type = None

    def set_file_type(self, file_type):
        """Set the current file type (INW or OUT)"""
        self.current_file_type = file_type

    def insert_file_header(self, cursor, prefix, header):
        # Set the current file type
        self.set_file_type(prefix)

        # Show warning for INW files
        if prefix == "INW":
            print(
                "WARNING: Security check field and hash total calculation may be incorrect or can occur errors."
            )

        query = f"""
        INSERT INTO {prefix}_FileHeader (BankControlId, FieldId, FileDate, BankCode, NumBatches, NumTransactions, Blank, FileName)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            header["BankControlId"],
            header["FieldId"],
            header["Date"],
            header["BankCode"],
            header["NoOfBatches"],
            header["NoOfTransactions"],
            " " * 155,
            header["FileName"],
        )
        cursor.execute(query, params)

    def insert_branch_header(self, cursor, prefix, header):
        query = f"""
        INSERT INTO {prefix}_BranchHeader (BranchControlId, FieldId, FileDate, BankCode, BranchCode, CreditTotal, NumCreditItems, DebitTotal, NumDebitItems, AccountHashTotal, Blank, FileName)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            header["BranchControlId"],
            header["FieldId"],
            header["Date"],
            header["BankCode"],
            header["BranchCode"],
            header["CreditTotal"],
            header["NoOfCreditItems"],
            header["DebitTotal"],
            header["NoOfDebitItems"],
            header["HashTotal"],
            " " * 101,
            header["FileName"],
        )
        cursor.execute(query, params)

    def validate_transaction(self, record):
        def is_valid_account(acc):
            acc_stripped = acc.strip()
            # Check if account is only numeric characters
            return acc_stripped.isdigit()

        return is_valid_account(record["DestAccount"]) and is_valid_account(
            record["OriginatingAccountNo"]
        )

    def insert_transaction(self, cursor, prefix, record):
        # Only validate and track invalid transactions for OUT files
        if prefix == "OUT" and (not self.validate_transaction(record)):
            self.invalid_transactions.append(record)
            return  # Skip insertion for invalid transactions in OUT files

        # For INW files, insert all transactions without validation
        query = f"""
        INSERT INTO {prefix}_Transaction (
            Transaction_Id, Destination_Bank_No, Destination_Branch_No, Destination_Ac_No,
            Destination_Ac_Name, Transaction_Code, Return_Code, Filler, Original_Transaction_Date,
            Amount, Currency_Code, Originating_Bank_No, Originating_Branch_No,
            Originating_Ac_No, Originating_Ac_Name, Particular, Reference, Value_Date,
            Security_Check_Field, Blank, FileName, AmountInt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record["TransactionId"],
            record["DestBank"],
            record["DestBranch"],
            record["DestAccount"],
            record["DestName"],
            record["TransactionCode"],
            record["ReturnCode"],
            record["Filler"],
            record["ReturnDate"],
            record["Amount"],
            record["Currency"],
            record["OriginatingBankNo"],
            record["OriginatingBranchNo"],
            record["OriginatingAccountNo"],
            record["OriginatorAccountName"],
            record["Particular"],
            record["Reference"],
            record["ValueDate"],
            record["SecurityCheck"],
            " " * 30,
            record["FileName"],
            record["AmountInt"],
        )
        cursor.execute(query, params)

    def export_invalid_transactions(self, file_name, total_transactions_processed):
        if self.current_file_type != "OUT":
            print(
                f"INFO: No invalid transactions exported for {self.current_file_type} file type"
            )
            return

        base_path = self.config_dir.parent 
        output_dir = base_path / "output"

        try:
            output_dir.mkdir(exist_ok=True)
        except Exception as e:
            print(f"ERROR: Could not create folder {output_dir} → {e}")
            return

        # Change extension to .txt
        output_file = output_dir / f"invalid_transactions_{Path(file_name).stem}.txt"

        if not self.invalid_transactions:
            print("No invalid transactions found for OUT file.")
            return

        # Add error reasons
        for transaction in self.invalid_transactions:
            errors = []
            if not transaction["DestAccount"].strip().isdigit():
                errors.append("DestAccount invalid")
            if not transaction["OriginatingAccountNo"].strip().isdigit():
                errors.append("OriginatingAccountNo invalid")
            transaction["Error_Reason"] = "; ".join(errors)

        try:
            with open(output_file, "w", encoding="utf-8") as txtfile:
                # Get ValueDate from first transaction (assuming all have same ValueDate)
                value_date = (
                    self.invalid_transactions[0]["ValueDate"]
                    if self.invalid_transactions
                    else ""
                )

                # Write header
                txtfile.write(f"DATE\t\t: {value_date}\n")
                txtfile.write(f"OWD FILE NAME\t: {file_name}\n\n")

                # Write column headers with tabs
                txtfile.write("-" * 177 + "\n")
                txtfile.write(
                    "FROM AC\t\tFROM BRANCH\tAMOUNT\t\tTO AC\t\tTO BANK\t\tTO BRANCH\tTO NAME\t\t\tTC\tREJECT REASON\n"
                )
                txtfile.write("-" * 177 + "\n")

                # Write invalid transactions (tab-separated)
                for transaction in self.invalid_transactions:
                    # Convert amount to decimal format (divide by 100, 2 decimal places)
                    try:
                        # Remove any non-numeric characters from amount first
                        amount_str = transaction["Amount"].strip()
                        # Extract numeric part (remove currency symbols, etc.)
                        numeric_part = "".join(filter(str.isdigit, amount_str))
                        if numeric_part:
                            amount_decimal = float(numeric_part) / 100
                            formatted_amount = f"{amount_decimal:.2f}"
                        else:
                            formatted_amount = "0.00"
                    except (ValueError, TypeError):
                        formatted_amount = "0.00"

                    line = (
                        f"{transaction['OriginatingAccountNo'].strip()}\t"
                        f"{transaction['OriginatingBranchNo'].strip()}\t\t"
                        f"{formatted_amount}\t\t"
                        f"{transaction['DestAccount'].strip()}\t"
                        f"{transaction['DestBank'].strip()}\t\t"
                        f"{transaction['DestBranch'].strip()}\t\t"
                        f"{transaction['DestName']}\t"
                        f"{transaction['TransactionCode'].strip()}\t"
                        f"{transaction['Error_Reason']}\n"
                    )
                    txtfile.write(line)

                # Write summary statistics
                valid_count = total_transactions_processed - len(
                    self.invalid_transactions
                )
                invalid_count = len(self.invalid_transactions)

                txtfile.write(f"\nVALID TXN\t: {valid_count}\n")
                txtfile.write(f"INVALID TXN\t: {invalid_count}\n")
                txtfile.write("-" * 25 + "\n")
                txtfile.write(f"TOTAL\t\t: {total_transactions_processed}\n")

            print(f"Invalid OUT transactions exported to {output_file}")

        except Exception as e:
            print(f"ERROR: Failed to write TXT file {output_file} → {e}")

    def insertion_statistics(self, cursor, prefix):
        query = (
            f"SELECT COUNT(*), SUM(CAST(AmountInt AS BIGINT)) FROM {prefix}_Transaction"
        )
        cursor.execute(query)
        result = cursor.fetchone()
        transaction_count = result[0] or 0
        total_amount = (result[1] or 0) / 100

        print(f"Total transactions inserted: {transaction_count}")
        print(f"Total Amount: {total_amount:.2f}")
        print("=" * 50)


class FileHandler:
    def __init__(self, input_dir):
        self.input_dir = input_dir

    def get_files(self):
        return [f for f in self.input_dir.iterdir() if f.is_file()]

    def archive_file(self, file_path):
        archive_dir = self.input_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / file_path.name

        if archive_path.exists():
            archive_path.unlink()
            
        file_path.rename(archive_path)


class SLIPSProcessor:
    def __init__(self, config_dir: Path, input_dir: Path):
        self.config_loader = ConfigLoader(config_dir)
        self.file_handler = FileHandler(input_dir)
        self.parser = RecordParser(self.config_loader.transaction_codes)

        # Use SQLite database in root directory
        root_dir = config_dir.parent  # This should be the base_path
        db_path = root_dir / "SLIPS.db"
        self.db_manager = DatabaseManager(str(db_path))

    def process(self):
        files = self.file_handler.get_files()

        if not files:
            print("No files found.")
            return

        file_path = files[0]
        with open(file_path, "r", encoding="utf-8") as f:
            dataset = f.read()

        parsed_data = self.parser.parse_dataset(dataset, file_path.name)

        if not parsed_data:
            print("No valid data found.")
            return

        cursor = self.db_manager.connect()

        if cursor:
            inserter = DataInserter(self.db_manager, self.config_loader.config_dir)
            total_transactions = 0

            for group in parsed_data:
                # In database fieldId = "IN " - INWARD
                # In database fieldId = "OUT" - OUTWARD
                prefix = "INW" if group["type"] == "IN " else "OUT"
                self.db_manager.clear_tables(cursor, prefix)
                inserter.insert_file_header(cursor, prefix, group["header1"])

                for branch in group["branches"]:
                    inserter.insert_branch_header(cursor, prefix, branch["header2"])
                    total_transactions += len(
                        branch["data"]
                    )  # Count total transactions

                    for record in branch["data"]:
                        inserter.insert_transaction(cursor, prefix, record)

            inserter.insertion_statistics(cursor, prefix)
            self.db_manager.commit_and_close()

            # Pass total transactions count to export method
            inserter.export_invalid_transactions(file_path.name, total_transactions)

        self.file_handler.archive_file(file_path)


def main(base_path: Path):
    """Main function to be called from other files"""
    processor = SLIPSProcessor(
        base_path / "config",  # Absolute path to config folder
        base_path / "input"    # Absolute path to input folder
    )
    processor.process()


if __name__ == "__main__":
    def get_local_base_path() -> Path:
        """Helper to get base path when running outside the main application structure."""
        return Path(__file__).parent.parent 
        
    main(get_local_base_path())
