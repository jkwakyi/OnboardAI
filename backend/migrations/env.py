"""Alembic environment for the Main Database.

The URL comes from the application settings rather than alembic.ini, so a
migration cannot be applied to a different database than the one the backend
talks to, and no credentials sit in a committed file.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings

# Importing the models registers every table on Base.metadata; without this
# `alembic revision --autogenerate` would see an empty schema and propose
# dropping all of them.
from app.db import models  # noqa: F401
from app.db.session import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`, which is not the default. Alembic
    # is not always a command line: the migration tests call
    # `command.upgrade` inside the test process, and the default would
    # switch off every logger that already existed - which is every logger
    # in the application - for the rest of that process.
    #
    # Nothing announces that. The application keeps running and simply
    # stops saying anything, so a later test asserting "this warns" sees
    # an empty log and a later test asserting "this does not warn" passes
    # without the code being run at all. The second is the dangerous one,
    # and it is how this was found: the first test to assert on a log
    # after the migration tests was the one that failed.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# A caller may set the URL itself - the tests run this migration against
# a throwaway SQLite file. Only fall back to the application settings.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or a DBA."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without this a column whose type changed is silently ignored.
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
