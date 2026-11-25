from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.models import Base

config = context.config


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        connection.dialect.ischema_names["vector"] = Vector  # type: ignore[attr-defined]
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
