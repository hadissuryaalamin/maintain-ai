"""Create and seed the configured local database."""

from __future__ import annotations

import json

from app.config import get_settings
from app.db.seed import seed_database
from app.db.session import get_database


def main() -> None:
    settings = get_settings()
    database = get_database()
    database.create_schema()
    with database.session() as session:
        counts = seed_database(session, settings.data_path)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
