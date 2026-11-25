"""A throwaway database, so eval numbers never mix with application data."""

from collections.abc import Iterator
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings

EVAL_DB = "placement_eval"


def eval_url() -> str:
    return get_settings().database_url.rsplit("/", 1)[0] + f"/{EVAL_DB}"


@contextmanager
def eval_session() -> Iterator[Session]:
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {EVAL_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {EVAL_DB}"))
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", eval_url())
    command.upgrade(config, "head")
    engine = create_engine(eval_url())
    try:
        with Session(engine, expire_on_commit=False) as db:
            yield db
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {EVAL_DB} WITH (FORCE)"))
        admin.dispose()
