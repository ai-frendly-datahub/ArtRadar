from __future__ import annotations

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
