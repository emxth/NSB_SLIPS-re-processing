# SLIP File Processing System — README

This repository contains a Python-based SLIP (Single-Line Input File Format) processing system that supports two main operations:
- Inserting SLIP file data into a local SQLite database.
- Recreating (exporting) SLIP files from the database (with validation, totals, security field calculation, and formatting).

Below is a concise guide to the repository layout, important files and classes, the runtime workflow, how to run the system, and common troubleshooting notes.

---

## Repository layout (folders & important files)

- input/ (input repository)
  - Place a single SLIP file (INW or OUT) here before starting insertion. The program processes only one file at a time.
  - After processing, the file is automatically moved to input/archive/.

- input/archive/
  - The program automatically moves processed input files here.

- config/ (config repository)
  - `bank_holidays.json` — Bank holidays used to compute next working day (used when creating OUT files).
  - `transaction_codes.json` — Master list of transaction codes used to classify records (Credit/Debit), compute totals and validate transactions.
  - `transaction_codes_mapping.json` — Mappings to convert old/invalid transaction codes into current/valid codes.

- output/ (output repository)
  - Re-created (exported) SLIP files and a text list of invalid OUT transactions are written here.

- SLIPS.db
  - The local SQLite database used by the system (created by the schema script).

- main.py
  - Application entry point and main menu controller.

- scripts/
  - `SLIPS-database-creation.sql` — SQL schema for creating the database tables.
  - `init_sqlite_db.py` — Utility to create `SLIPS.db` by executing the SQL schema.
  - `SLIPS_insertion.py` — Insertion workflow that parses input files and inserts records into the DB.
  - `SLIPS_recreation.py` — Recreation workflow that prepares data and writes SLIP output files.

---

## Key files & classes (quick reference)

Note: Class and method names below map to the major responsibilities in the system.

- main.py
  - get_base_path() — determines application base directory (works for script & PyInstaller exe).
  - show_menu(), clear_screen() — text UI.
  - run_insertion(), run_recreation() — loads and runs `SLIPS_insertion` or `SLIPS_recreation`.

- scripts/init_sqlite_db.py
  - Reads `SLIPS-database-creation.sql` and creates `SLIPS.db`.

- scripts/SLIPS_insertion.py
  - ConfigLoader — loads `transaction_codes.json`.
  - DatabaseManager — opens SQLite connection, enforces FK, clears tables for insertion.
  - RecordParser — parses fixed-width SLIP files (markers: `5555` = file header, `4444` = branch header, `0000` = transaction).
    - parse_header1(), parse_header2(), parse_data_record(), parse_dataset(), find_branch_data(), find_transactions()
  - DataInserter — inserts file/branch/transaction rows, validates OUT transactions (numeric account numbers), exports invalid OUT transactions to `output/`.
  - FileHandler — finds files in input/ and archives processed files.
  - SLIPSProcessor — orchestrates read → parse → insert → stats → archive.

- scripts/SLIPS_recreation.py
  - Settings — path & config loader, constants (CUTOFF_TIME = 15:00), passwords (BANK_PW, LANKA_CLEAR_PW).
  - Database — robust SQLite connection (WAL, timeout, foreign keys), close_safely().
  - CodeMappingService — loads `transaction_codes.json` and `transaction_codes_mapping.json`, updates incorrect codes in DB.
  - Formatters — helpers to format numbers and amounts for fixed-width fields.
  - TransactionAnalyzer — classifies credit/debit, computes credit/debit totals and hash totals; halts on unknown codes and prompts mapping/database update.
  - BranchService — updates branch totals and status; supports refetch/retry if mappings change during processing.
  - BranchInspector — filters/excludes branches with only zero-value transactions or other problems.
  - SecurityFieldCalculator — low-level algorithm that computes 6-digit Security Check Field from passwords, accounts, codes and amount.
  - TransactionSecurityUpdater — computes and writes Security_Check_Field for all transactions (after safety checks).
  - ValueDateService — loads holidays, computes next working day, suggests value dates based on cutoff time (3 PM).
  - OutFileCleanupService — final SQL fixes (zero-padding destination account, default fields, return codes, etc).
  - ValueDateUpdater — stamps normal vs. salary value dates on transactions.
  - FileHeaderService — manages file header totals and status flags.
  - FileRecreator — formats fh_line, bh_line, tx_line and writes final single-line SLIP file to `output/`.
  - TransactionStatistics — prints final counts and totals.
  - Helpers — small utilities (e.g., table prefix detection).
  - Orchestrator — high-level workflow controller for OUT and INW processing.
  - MemoryCleanup — calls gc.collect() for a clean exit.

---

## End-to-end workflows

1. Initialize database (one-time)
   - From repository root: python scripts/init_sqlite_db.py
   - This creates `SLIPS.db` by executing `scripts/SLIPS-database-creation.sql`.

2. Insert a SLIP file
   - Put a single input file (INW or OUT) in `input/`.
   - Run: python main.py → choose "1. Insert SLIP data to database".
   - `SLIPS_insertion` components:
     - `FileHandler` locates the file.
     - `RecordParser` parses headers and transactions.
     - `DataInserter` writes to the DB (OUT transactions are validated; invalid ones are recorded and exported to `output/`).
     - Processed file moved to `input/archive/`.

3. Recreate (export) SLIP file
   - Run: python main.py → choose "2. Recreate SLIP file from database".
   - `SLIPS_recreation` orchestrator runs steps for OUT or INW:
     - Value date calculation (OUT only), cleanup, totals update, security field computation, final file writing (single-line format).
   - The final SLIP file and any invalid-transaction reports are written to `output/`.

---

## Important business rules & markers

- File markers in raw input:
  - File header starts at marker `5555`
  - Branch header marker: `4444`
  - Transaction record marker: `0000`
- For OUT files:
  - Both originating and destination account numbers must be numeric — otherwise transaction is treated as invalid and recorded in `output/` as rejected.
- Cutoff time for value date suggestion: 15:00 (3 PM).
- Security Check Field: 6-digit computed field — must be set for every transaction before export.

---

## Common troubleshooting

- Database locked errors: Ensure no other process is writing to `SLIPS.db`. Recreation uses WAL and a 10s timeout, but you can close other connections.
- Unknown transaction codes during recreation: Update `transaction_codes_mapping.json` or run `CodeMappingService.update_transaction_codes_in_database()` (the recreation workflow can prompt & refetch).
- Invalid transactions file: Check `output/` for the exported list of invalid OUT transactions (contains reasons and counts).
- Holidays wrong/missing: Update `config/bank_holidays.json` for the current year to ensure correct value date calculation.

---

## Development notes & tips

- Paths: `main.py` resolves a base application path with `get_base_path()` so the system works both as a script and as a PyInstaller-bundled executable.
- Run `init_sqlite_db.py` any time you need to recreate the schema (this will create an empty `SLIPS.db`).
- All configuration is JSON in the `config/` directory — keep transaction code lists and mappings up-to-date.
- Use the `transaction_codes_mapping.json` to migrate old codes automatically during recreation.

---

## CMD Commands

To build .EXE file, run. After build, move .exe file into root.

```bash
pyinstaller --onefile --name "SLIP_Processor" ^
--collect-all sqlite3 ^
--hidden-import SLIPS_insertion ^
--hidden-import SLIPS_recreation ^
--add-data "scripts;scripts" ^
main.py
```

