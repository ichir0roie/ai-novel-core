from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, text

from db.postgres.postgis import POSTGIS_COLUMNS, POSTGIS_TABLES
from db.schema import DATABASE_IAM_AUTH, Base, database_url, make_url_engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# db/schema.py と同じ db(DEM_DATABASE_URL)を使う。RDS に当てるときは tool.aws.rds がマスターの URL を渡す。
# URL の % は configparser の補間に食われるので重ねる
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 表の持ち主のロール(infra/sql/novel_migrator.sql)。マスターから流すときも、このロールで表を作る・変える
MIGRATION_ROLE = "novel_migrator"

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


def _as_migration_role(connection: Connection) -> None:
    """この db の表の持ち主が `MIGRATION_ROLE` で、自分がそれに入っていれば(AWS の db にマスターで繋いだとき)SET ROLE する。
    新しい表の持ち主がそのロールになり、そのロールに掛けた既定の権限で novel_app が読み書きできる。
    手元の開発用の db は表の持ち主が別なので何もしない。"""
    member = connection.scalar(
        text("SELECT pg_has_role(current_user, tableowner, 'MEMBER') AND current_user <> tableowner FROM pg_tables "
             "WHERE schemaname = 'public' AND tablename = 'alembic_version' AND tableowner = :role"),
        {"role": MIGRATION_ROLE})
    if member:
        connection.execute(text(f"SET ROLE {MIGRATION_ROLE}"))
    # SET ROLE は接続に残る。下の begin_transaction が自分で commit するよう、問い合わせで始まったトランザクションを閉じる
    connection.commit()


def run_migrations_online() -> None:
    # 手元のふだんの接続(novel_app)は IAM 認証のトークンで繋ぐので、schema.py と同じ作り方で engine を作る
    connectable = make_url_engine(database_url(), iam_auth=DATABASE_IAM_AUTH)

    with connectable.connect() as connection:
        _as_migration_role(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
