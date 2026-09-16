"""Apply the SQL schema files to the project database.

Every file in infra/sql is idempotent (`create ... if not exists`), so this runs safely
as many times as you like. Files are applied in filename order.

    python -m pipeline.db.migrate
"""

from __future__ import annotations

from pipeline.config import SQL_DIR
from pipeline.db import connect


def apply_schema(dsn: str | None = None) -> list[str]:
    """Run every SQL file in infra/sql; returns the filenames applied, in order."""
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise RuntimeError(f"No SQL files found in {SQL_DIR}")
    with connect(dsn) as conn:
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
    return [path.name for path in files]


def main() -> None:
    for name in apply_schema():
        print(f"applied {name}")


if __name__ == "__main__":
    main()
