"""Persist each cycle to SQLite and append to a CSV."""
from __future__ import annotations

import csv
import os
import sqlite3
from typing import Optional

FIELDS = [
    "ts",
    "soc",
    "solar_w",
    "load_w",
    "grid_w",
    "battery_w",
    "grid_status",
    "import_p",
    "export_p",
    "action",
    "mode",
    "reserve",
    "grid_charging",
    "note",
]

_CREATE = (
    "CREATE TABLE IF NOT EXISTS cycles ("
    "ts TEXT, soc REAL, solar_w REAL, load_w REAL, grid_w REAL, battery_w REAL, "
    "grid_status TEXT, import_p REAL, export_p REAL, action TEXT, mode TEXT, "
    "reserve REAL, grid_charging INTEGER, note TEXT)"
)


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE)
        conn.commit()
    finally:
        conn.close()


def _normalise(record: dict) -> dict:
    row = {k: record.get(k) for k in FIELDS}
    # store booleans as 0/1 for SQLite friendliness
    gc = row.get("grid_charging")
    row["grid_charging"] = int(bool(gc)) if gc is not None else None
    return row


def append(db_path: str, csv_path: str, record: dict) -> None:
    row = _normalise(record)

    # SQLite
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in FIELDS)
        conn.execute(
            f"INSERT INTO cycles ({','.join(FIELDS)}) VALUES ({placeholders})",
            [row[k] for k in FIELDS],
        )
        conn.commit()
    finally:
        conn.close()

    # CSV (write header if new/empty)
    new_file = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
    with open(csv_path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
