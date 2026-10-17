from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parent.parent


def test_migrations_upgrade_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrate.sqlite3'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    assert {"users", "parcels", "tracking_events"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("parcels")} >= {"tracking_number", "price_total", "status"}

    command.downgrade(cfg, "base")
    assert not {"users", "parcels", "tracking_events"} & set(inspect(create_engine(url)).get_table_names())
