import os, sys
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
load_dotenv(APP_DIR / ".env")

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.models import Base

config = context.config
target_metadata = Base.metadata

def get_url():
    url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")
    return url

def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
