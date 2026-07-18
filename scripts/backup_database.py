
from __future__ import annotations

import gzip
import json
import os
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

TABLES = ("products", "orders", "order_items")


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported type: {type(value)!r}")


def main():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")

    project = Path(__file__).resolve().parents[1]
    output_dir = project / "_onlycards_db_backups" / "postgres"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"onlycards_backup_{timestamp}.json.gz"

    payload = {
        "format": "onlycards-postgres-json-v1",
        "created_at": datetime.now().isoformat(),
        "tables": {},
    }

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(f'SELECT * FROM "{table}" ORDER BY id')
                payload["tables"][table] = cursor.fetchall()

    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )

    print(f"Backup created: {output_path}")
    print("This file contains customer data. Keep it private and outside Git.")


if __name__ == "__main__":
    main()
