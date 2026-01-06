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

