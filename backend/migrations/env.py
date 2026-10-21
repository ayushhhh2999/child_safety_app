from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.database import Base, database_url
from app.models.connection import Connection, SharingPermission
from app.models.login_attempt import FailedLoginAttempt
from app.models.user import User


config = context.config
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_registered_models = (Connection, SharingPermission, FailedLoginAttempt, User)
if any(
    target_metadata.tables.get(model.__tablename__) is not model.__table__
    for model in _registered_models
):
    raise RuntimeError("Alembic model metadata is incomplete")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


settings.validate_startup()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
