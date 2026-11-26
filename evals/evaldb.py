"""A throwaway database, so eval numbers never mix with application data."""

from collections.abc import Iterator
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings

EVAL_DB = "placement_eval"


def eval_url(name: str = EVAL_DB) -> str:
    return get_settings().database_url.rsplit("/", 1)[0] + f"/{name}"


@contextmanager
def scratch_database(name: str) -> Iterator[str]:
    """Create a migrated, empty database, yield its URL and drop it afterwards."""
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {name}"))
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", eval_url(name))
    command.upgrade(config, "head")
    try:
        yield eval_url(name)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        admin.dispose()


@contextmanager
def eval_session() -> Iterator[Session]:
    with scratch_database(EVAL_DB) as url:
        engine = create_engine(url)
        try:
            with Session(engine, expire_on_commit=False) as db:
                yield db
        finally:
            engine.dispose()
