"""Exercise upgrade on an existing database, including pending allocations."""

import sqlite3

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def test_tracking_migration_preserves_balances_units_and_snapshots(tmp_path, monkeypatch):
    database = tmp_path / "migration.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "b2c3d4e5f6a7")
        with sqlite3.connect(database) as db:
            # SQLite fixture uses synthetic FK identities; the migration does not modify them.
            for identifier, amount, price in [("balance", 1000, None), ("units", 2, 500)]:
                db.execute(
                    "INSERT INTO positions (id,user_id,portfolio_id,name,asset_type,amount,current_price,strength,source) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        "user",
                        "portfolio",
                        identifier,
                        "rendafixa",
                        amount,
                        price,
                        0,
                        "user",
                    ),
                )
                db.execute(
                    "INSERT INTO aporte_allocations (id,aporte_event_id,position_id,position_name_snapshot,asset_type_snapshot,price_at_aporte_brl,suggested_value_brl,suggested_quantity,applied,excluded) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        "event",
                        identifier,
                        identifier,
                        "rendafixa",
                        price,
                        100,
                        1 if price is None else 0.2,
                        0,
                        0,
                    ),
                )
        command.upgrade(config, "head")
        with sqlite3.connect(database) as db:
            assert db.execute(
                'SELECT amount,current_price,tracking_mode FROM positions WHERE id="balance"'
            ).fetchone() == (1000, None, "balance")
            assert db.execute(
                'SELECT amount,current_price,tracking_mode FROM positions WHERE id="units"'
            ).fetchone() == (2, 500, "units")
            assert db.execute(
                "SELECT tracking_mode_snapshot FROM aporte_allocations ORDER BY id"
            ).fetchall() == [("balance",), ("units",)]
            assert db.execute("SELECT count(*) FROM auth_sessions").fetchone() == (0,)
        command.downgrade(config, "b2c3d4e5f6a7")
        with sqlite3.connect(database) as db:
            assert db.execute(
                'SELECT amount,current_price FROM positions WHERE id="balance"'
            ).fetchone() == (1000, None)
    finally:
        get_settings.cache_clear()
