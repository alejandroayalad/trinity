"""Run explicit migrations using the configured PostgreSQL connection."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from trinity.config import load_api_settings


def run_migrations() -> None:
    """Apply reviewed revisions; never log the database connection string."""
    from sqlalchemy.engine import make_url
    engine = None
    try:
        url = make_url(load_api_settings().database_url.get_secret_value())
        url = url.set(drivername="postgresql+psycopg")
        engine = create_engine(url, poolclass=NullPool, echo=False,
                               connect_args={"connect_timeout": 5,
                                             "options": "-c statement_timeout=30000 -c lock_timeout=5000"})
        with engine.connect() as connection:
            context.configure(connection=connection, transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
    except Exception:
        raise RuntimeError("Database migration failed; inspect schema and connectivity locally.") from None
    finally:
        if engine is not None:
            engine.dispose()



run_migrations()
