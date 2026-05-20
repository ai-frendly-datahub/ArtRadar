from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from artradar.search_index import SearchIndex


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


@pytest.mark.unit
def test_mcp_path_helpers_and_scalar_coercion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from artradar.mcp_server import server

    env_db = tmp_path / "env.duckdb"
    env_db.write_text("db", encoding="utf-8")
    monkeypatch.setenv("RADAR_DB_PATH", str(env_db))
    monkeypatch.setenv("RADAR_SEARCH_DB_PATH", str(tmp_path / "search.db"))

    assert server._db_path() == env_db
    assert server._search_db_path() == tmp_path / "search.db"
    assert server._as_int(True, 7) == 7
    assert server._as_int("12", 7) == 12
    assert server._as_int("bad", 7) == 7
    assert server._as_int(5.5, 7) == 7
    assert server._as_float(False, 1.5) == 1.5
    assert server._as_float(2, 1.5) == 2.0
    assert server._as_float("3.25", 1.5) == 3.25
    assert server._as_float("bad", 1.5) == 1.5
    assert server._as_float(object(), 1.5) == 1.5


@pytest.mark.unit
def test_mcp_db_path_uses_template_default_when_settings_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from artradar.mcp_server import server

    default_db = tmp_path / "data" / "art_data.duckdb"
    default_db.parent.mkdir()
    default_db.write_text("db", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RADAR_DB_PATH", raising=False)
    monkeypatch.setattr(
        server,
        "load_settings",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing config")),
    )

    assert server._db_path().resolve() == default_db.resolve()


@pytest.mark.unit
def test_mcp_coerce_args_and_tool_specs() -> None:
    from artradar.mcp_server import server

    assert server._coerce_args(None) == {}
    assert server._coerce_args({1: "ignored", "query": "art"}) == {"query": "art"}

    specs = server._list_tool_specs()
    assert [spec["name"] for spec in specs] == [
        "search",
        "recent_updates",
        "sql",
        "top_trends",
        "price_watch",
    ]


@pytest.mark.unit
def test_mcp_tool_helpers_cover_empty_rows_and_empty_link_filter(tmp_path: Path) -> None:
    from artradar.mcp_server import tools

    db_path = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE articles (link TEXT, collected_at TIMESTAMP)")
    finally:
        con.close()

    assert tools._format_rows(["title"], []) == "No rows returned."
    assert tools._filter_links_by_days(db_path=db_path, links=[], days=7) == set()


@pytest.mark.unit
def test_mcp_call_tool_handler_dispatches_all_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from artradar.mcp_server import server

    search_db = tmp_path / "search.db"
    article_db = tmp_path / "articles.duckdb"
    monkeypatch.setattr(server, "_search_db_path", lambda: search_db)
    monkeypatch.setattr(server, "_db_path", lambda: article_db)
    monkeypatch.setattr(
        server,
        "handle_search",
        lambda *, search_db_path, db_path, query, limit: (
            f"search:{search_db_path.name}:{db_path.name}:{query}:{limit}"
        ),
    )
    monkeypatch.setattr(
        server,
        "handle_recent_updates",
        lambda *, db_path, days, limit: f"recent:{db_path.name}:{days}:{limit}",
    )
    monkeypatch.setattr(
        server,
        "handle_sql",
        lambda *, db_path, query: f"sql:{db_path.name}:{query}",
    )
    monkeypatch.setattr(
        server,
        "handle_top_trends",
        lambda *, db_path, days, limit: f"trends:{db_path.name}:{days}:{limit}",
    )
    monkeypatch.setattr(
        server,
        "handle_price_watch",
        lambda *, threshold: f"price:{threshold}",
    )

    assert (
        server._call_tool_handler("search", {"query": "art", "limit": "3"})
        == "search:search.db:articles.duckdb:art:3"
    )
    assert (
        server._call_tool_handler("recent_updates", {"days": "bad", "limit": True})
        == "recent:articles.duckdb:7:20"
    )
    assert server._call_tool_handler("sql", {"query": "SELECT 1"}) == "sql:articles.duckdb:SELECT 1"
    assert (
        server._call_tool_handler("top_trends", {"days": 2, "limit": 4})
        == "trends:articles.duckdb:2:4"
    )
    assert server._call_tool_handler("price_watch", {"threshold": "1.25"}) == "price:1.25"
    assert server._call_tool_handler("missing", {"query": "art"}) == "Unknown tool: missing"


@pytest.mark.unit
def test_mcp_create_app_registers_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    from artradar.mcp_server import server

    class FakeApp:
        def __init__(self, name: str) -> None:
            self.name = name
            self.list_tools_handler: Any = None
            self.call_tool_handler: Any = None

        def list_tools(self) -> Any:
            def decorator(func: Any) -> Any:
                self.list_tools_handler = func
                return func

            return decorator

        def call_tool(self) -> Any:
            def decorator(func: Any) -> Any:
                self.call_tool_handler = func
                return func

            return decorator

        async def run(self, read_stream: object, write_stream: object, options: object) -> None:
            raise AssertionError("run should not be called by create_app")

        def create_initialization_options(self) -> object:
            return object()

    fake_app = FakeApp("pending")

    def fake_import_module(name: str) -> object:
        if name == "mcp.server":
            return SimpleNamespace(Server=lambda server_name: fake_app)
        if name == "mcp.types":
            return SimpleNamespace(
                Tool=lambda **kwargs: {"tool": kwargs},
                TextContent=lambda **kwargs: {"text": kwargs},
            )
        raise AssertionError(name)

    monkeypatch.setattr(server, "import_module", fake_import_module)
    monkeypatch.setattr(server, "_call_tool_handler", lambda name, arguments: f"{name}:{arguments}")

    app = server.create_app()

    assert app is fake_app
    assert fake_app.name == "pending"
    tools = asyncio.run(fake_app.list_tools_handler())
    assert tools[0]["tool"]["name"] == "search"
    result = asyncio.run(fake_app.call_tool_handler("search", {"query": "art"}))
    assert result == [{"text": {"type": "text", "text": "search:{'query': 'art'}"}}]


@pytest.mark.unit
def test_mcp_main_runs_stdio_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from artradar.mcp_server import server

    events: list[tuple[str, object, object, object]] = []

    class FakeContext:
        async def __aenter__(self) -> tuple[str, str]:
            return "read", "write"

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: object,
        ) -> None:
            return None

    class FakeApp:
        async def run(self, read_stream: object, write_stream: object, options: object) -> None:
            events.append(("run", read_stream, write_stream, options))

        def create_initialization_options(self) -> str:
            return "options"

    monkeypatch.setattr(server, "create_app", lambda: FakeApp())
    monkeypatch.setattr(
        server,
        "import_module",
        lambda name: SimpleNamespace(stdio_server=lambda: FakeContext()),
    )

    asyncio.run(server.main())

    assert events == [("run", "read", "write", "options")]


def _create_articles_db(db_path: Path) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute("""
            CREATE TABLE articles (
                title TEXT,
                source TEXT,
                link TEXT,
                collected_at TIMESTAMP,
                entities_json TEXT
            )
            """)
        now = datetime.now(UTC).replace(tzinfo=None)
        old = (datetime.now(UTC) - timedelta(days=30)).replace(tzinfo=None)
        con.executemany(
            """
            INSERT INTO articles (title, source, link, collected_at, entities_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "Modern Art",
                    "Artnet",
                    "https://example.com/modern",
                    now,
                    json.dumps({"Genre": ["painting", "sculpture"]}),
                ),
                (
                    "Old Art",
                    "Archive",
                    "https://example.com/old",
                    old,
                    json.dumps({"Period": ["renaissance"]}),
                ),
                ("No Entities", "Archive", "https://example.com/none", now, ""),
            ],
        )
    finally:
        con.close()


@pytest.mark.unit
def test_mcp_handle_search_with_natural_language_time_filter(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_search

    db_path = tmp_path / "articles.duckdb"
    search_db_path = tmp_path / "search.db"
    _create_articles_db(db_path)
    with SearchIndex(search_db_path) as idx:
        idx.upsert("https://example.com/modern", "Modern Art", "modern painting")
        idx.upsert("https://example.com/old", "Old Art", "modern archive")

    result = handle_search(
        search_db_path=search_db_path,
        db_path=db_path,
        query="최근 7일 modern top 5",
    )

    assert "Modern Art" in result
    assert "Old Art" not in result


@pytest.mark.unit
def test_mcp_handle_search_empty_and_non_positive_limit(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_search

    db_path = tmp_path / "articles.duckdb"
    search_db_path = tmp_path / "search.db"
    _create_articles_db(db_path)
    with SearchIndex(search_db_path):
        pass

    assert (
        handle_search(search_db_path=search_db_path, db_path=db_path, query="   ", limit=10)
        == "No results found."
    )
    assert (
        handle_search(search_db_path=search_db_path, db_path=db_path, query="art", limit=0)
        == "No results found."
    )


@pytest.mark.unit
def test_mcp_handle_recent_updates_and_sql(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_recent_updates, handle_sql

    db_path = tmp_path / "articles.duckdb"
    _create_articles_db(db_path)

    recent = handle_recent_updates(db_path=db_path, days=7, limit=5)
    assert "Modern Art" in recent
    assert "Old Art" not in recent
    assert handle_recent_updates(db_path=db_path, days=7, limit=0) == "No recent updates found."

    sql = handle_sql(db_path=db_path, query="SELECT title FROM articles ORDER BY title LIMIT 1")
    assert "Modern Art" in sql or "No Entities" in sql
    assert handle_sql(db_path=db_path, query="DELETE FROM articles").startswith("Error:")
    assert handle_sql(db_path=db_path, query="SELECT * FROM missing_table").startswith("Error:")


@pytest.mark.unit
def test_mcp_handle_recent_updates_and_sql_empty_results(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_recent_updates, handle_sql

    db_path = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("""
            CREATE TABLE articles (
                title TEXT,
                source TEXT,
                link TEXT,
                collected_at TIMESTAMP
            )
            """)
    finally:
        con.close()

    assert handle_recent_updates(db_path=db_path, days=7, limit=5) == "No recent updates found."
    assert handle_sql(db_path=db_path, query="SELECT title FROM articles") == "No rows returned."


@pytest.mark.unit
def test_mcp_handle_top_trends_and_price_watch(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_price_watch, handle_top_trends

    db_path = tmp_path / "articles.duckdb"
    _create_articles_db(db_path)

    trends = handle_top_trends(db_path=db_path, days=7, limit=3)
    assert "Top trends:" in trends
    assert "Genre: 2" in trends
    assert handle_top_trends(db_path=db_path, days=7, limit=0) == "No trend data available."
    assert handle_price_watch(threshold=100.0) == "Not available in template project"


@pytest.mark.unit
def test_mcp_top_trends_handles_invalid_json(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_top_trends

    db_path = tmp_path / "articles.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE articles (collected_at TIMESTAMP, entities_json TEXT)")
        con.execute(
            "INSERT INTO articles VALUES (?, ?)",
            [datetime.now(UTC).replace(tzinfo=None), "{not-json"],
        )
    finally:
        con.close()

    assert handle_top_trends(db_path=db_path, days=7, limit=5) == "No trend data available."


@pytest.mark.unit
def test_mcp_top_trends_skips_non_list_entity_values(tmp_path: Path) -> None:
    from artradar.mcp_server.tools import handle_top_trends

    db_path = tmp_path / "articles.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE articles (collected_at TIMESTAMP, entities_json TEXT)")
        con.executemany(
            "INSERT INTO articles VALUES (?, ?)",
            [
                [
                    datetime.now(UTC).replace(tzinfo=None),
                    json.dumps({"Genre": "painting", "Topic": ["review"]}),
                ],
            ],
        )
    finally:
        con.close()

    result = handle_top_trends(db_path=db_path, days=7, limit=5)

    assert "Topic: 1" in result
    assert "Genre" not in result
