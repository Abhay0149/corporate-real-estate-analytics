"""Build the Phase 3 SQLite database from the CLEAN Phase 2 CSVs.

ALL DATA IS SYNTHETIC. Reads data/clean/ only (never modifies it).

Usage:  python tests/build_database.py [--db PATH]
Default DB path: sql/cre_synthetic.sqlite  (generated file, safe to delete/rebuild)
"""
import argparse
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
SCHEMA = ROOT / "sql" / "01_schema.sql"

# Load order respects foreign keys.
TABLES = ["dim_location", "dim_cost_category", "dim_date",
          "fact_space_usage", "fact_opex", "fact_budget", "fact_projects"]


def build(db_path: Path) -> sqlite3.Connection:
    if db_path != Path(":memory:") and db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text())
    for table in TABLES:
        with open(CLEAN / f"{table}.csv", newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            rows = [[None if v == "" else v for v in r] for r in reader]
        marks = ",".join("?" * len(header))
        con.executemany(f"INSERT INTO {table} ({','.join(header)}) VALUES ({marks})", rows)
    con.commit()
    return con


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "sql" / "cre_synthetic.sqlite"))
    args = ap.parse_args()
    con = build(Path(args.db))
    for t in TABLES:
        print(f"{t:20s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>6,} rows")
    print("Built", args.db, "(synthetic data)")
