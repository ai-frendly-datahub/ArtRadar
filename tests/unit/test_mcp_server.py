from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_mcp_server_imports() -> None:
    from artradar.mcp_server.server import create_app
    from artradar.mcp_server.tools import (
        handle_price_watch,
        handle_recent_updates,
        handle_search,
        handle_sql,
        handle_top_trends,
    )

    assert callable(create_app)
    assert callable(handle_search)
    assert callable(handle_recent_updates)
    assert callable(handle_sql)
    assert callable(handle_top_trends)
    assert callable(handle_price_watch)


@pytest.mark.unit
def test_mcp_db_path_falls_back_to_latest_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from artradar.mcp_server import server

    db_path = tmp_path / "data" / "art_data.duckdb"
    older = tmp_path / "data" / "snapshots" / "2026-03-12" / "art_data.duckdb"
    newer = tmp_path / "data" / "snapshots" / "2026-03-13" / "art_data.duckdb"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")

    monkeypatch.delenv("RADAR_DB_PATH", raising=False)
    monkeypatch.setattr(server, "load_settings", lambda: SimpleNamespace(database_path=db_path))

    assert server._db_path() == newer
