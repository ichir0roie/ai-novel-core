from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from db.postgres.postgis import POSTGIS_COLUMNS, POSTGIS_TABLES
from db.schema import Base, database_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# db/schema.py と同じ db(DEM_DATABASE_URL があればその PostgreSQL、無ければ DB_PATH の SQLite)を使う。
# URL の % は configparser の補間に食われるので重ねる
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(obj, name, type_, reflected, compare_to):
    """schema.py に無い、PostgreSQL 側だけの物(PostGIS の表・幾何の列)を autogenerate が消そうとしないよう外す。"""
    if type_ == "table" and reflected and compare_to is None and name in POSTGIS_TABLES:
        return False
    if type_ == "column" and reflected and compare_to is None and (obj.table.name, name) in POSTGIS_COLUMNS:
        return False
    if type_ == "index" and reflected and compare_to is None and name.startswith("ix_postgis_"):
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
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
            # SQLite は ALTER が弱いので表を作り直す batch で書く。PostgreSQL はそのまま ALTER する
            render_as_batch=connection.dialect.name == "sqlite",
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
