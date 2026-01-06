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

