"""Logging configuration shared by the API and CLI entry points."""

import logging


def configure_logging(app_env: str) -> None:
    level = logging.DEBUG if app_env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # SQLAlchemy engine logging is noisy; keep it at WARNING unless debugging SQL.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
