import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to values within the .ini file in use.
config = context.config

# Interpret the config file for Python's standard logging.
# This uses the default 'logging.conf' if it exists.
fileConfig(config.config_file_name)

# Add your project root to sys.path
# This assumes the alembic directory is directly inside the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import SQLModel metadata — models must be imported to register tables
from sqlmodel import SQLModel  # noqa: E402
import backend.models  # noqa: E402, F401 — registers all table models

target_metadata = SQLModel.metadata


# other values from the config, defined by the needs of env.py,
# can be acquired as a dictionary object using config.get_section(ini_section_name, {})
# and sqlalchemy.url from the .ini file
def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an actual DBAPI connection.
    Calls to context.execute() here emit the given string to the
    script output.

    """
    # Use DATABASE_URL from config.py directly if it's available
    # Or get it from the environment
    url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get database URL from alembic.ini or environment variable
    db_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = engine_from_config(
        {"sqlalchemy.url": db_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
