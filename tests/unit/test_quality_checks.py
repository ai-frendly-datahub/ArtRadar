from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from artradar.common import quality_checks


@pytest.fixture
def quality_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE articles (
            title TEXT,
            url TEXT,
            language TEXT,
            published_at TIMESTAMP
        )
        """)
    con.executemany(
        "INSERT INTO articles VALUES (?, ?, ?, ?)",
        [
            ("Modern Art", "https://example.com/a", "en", datetime.now(UTC)),
            ("", "https://example.com/a", "ko", datetime.now(UTC) + timedelta(days=1)),
            ("Auction", "https://example.com/b", "xx", datetime.now(UTC)),
        ],
    )
    try:
        yield con
    finally:
        con.close()


@pytest.mark.unit
def test_quality_check_helpers_cover_conversion_edges() -> None:
    con = duckdb.connect(":memory:")
    try:
        with pytest.raises(RuntimeError):
            quality_checks._fetchone_required(con, "SELECT 1 WHERE FALSE")
    finally:
        con.close()

    assert quality_checks._to_int(True) == 1
    assert quality_checks._to_int("3") == 3
    assert quality_checks._to_int(b"4") == 4
    assert quality_checks._to_optional_int(None) is None
    assert quality_checks._to_optional_float(None) is None
    assert quality_checks._to_optional_float(False) == 0.0
    assert quality_checks._to_optional_float("1.5") == 1.5

    with pytest.raises(TypeError):
        quality_checks._to_int(object())
    with pytest.raises(TypeError):
        quality_checks._to_optional_float(object())


@pytest.mark.unit
def test_check_missing_fields_handles_empty_table(capsys: pytest.CaptureFixture[str]) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE empty_articles (title TEXT)")
        quality_checks.check_missing_fields(
            con,
            table_name="empty_articles",
            null_conditions={"title": "title IS NULL OR title = ''"},
        )
    finally:
        con.close()

    assert "No records found." in capsys.readouterr().out


@pytest.mark.unit
def test_quality_checks_print_expected_findings(
    quality_db: duckdb.DuckDBPyConnection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quality_checks.check_missing_fields(
        quality_db,
        table_name="articles",
        null_conditions={"title": "title IS NULL OR title = ''"},
    )
    quality_checks.check_duplicate_urls(quality_db, table_name="articles", url_column="url")
    quality_checks.check_text_lengths(quality_db, table_name="articles", text_columns=["title"])
    quality_checks.check_language_values(
        quality_db,
        table_name="articles",
        language_column="language",
        allowed_languages={"en", "ko"},
    )
    quality_checks.check_dates(quality_db, table_name="articles")

    output = capsys.readouterr().out
    assert "title: 1 / 3 (33.3%)" in output
    assert "2x: https://example.com/a" in output
    assert "title: avg/min/max" in output
    assert "Invalid language values:" in output
    assert "xx: 1" in output
    assert "future dates: 1" in output


@pytest.mark.unit
def test_check_duplicate_urls_can_scope_by_group(
    capsys: pytest.CaptureFixture[str],
) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("""
            CREATE TABLE articles (
                category TEXT,
                url TEXT
            )
            """)
        con.executemany(
            "INSERT INTO articles VALUES (?, ?)",
            [
                ("art", "https://example.com/a"),
                ("art", "https://example.com/a"),
                ("artwork", "https://example.com/a"),
                ("artwork", "https://example.com/b"),
            ],
        )

        quality_checks.check_duplicate_urls(
            con,
            table_name="articles",
            url_column="url",
            group_columns=["category"],
        )
    finally:
        con.close()

    output = capsys.readouterr().out
    assert "category=art, 2x: https://example.com/a" in output
    assert "category=artwork" not in output


@pytest.mark.unit
def test_quality_checks_handle_no_duplicates_no_text_and_allowed_languages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("""
            CREATE TABLE articles (
                title TEXT,
                url TEXT,
                language TEXT,
                published_at TIMESTAMP
            )
            """)
        con.executemany(
            "INSERT INTO articles VALUES (?, ?, ?, ?)",
            [
                ("A", "https://example.com/a", "en", datetime.now(UTC)),
                ("B", "https://example.com/b", "ko", datetime.now(UTC)),
            ],
        )

        quality_checks.check_duplicate_urls(con, table_name="articles", url_column="url")
        quality_checks.check_text_lengths(con, table_name="articles", text_columns=[])
        quality_checks.check_language_values(
            con,
            table_name="articles",
            language_column="language",
            allowed_languages={"en", "ko"},
        )
    finally:
        con.close()

    output = capsys.readouterr().out
    assert "No duplicate URLs found." in output
    assert "No text columns provided." in output
    assert "All language values are allowed." in output


@pytest.mark.unit
def test_check_language_values_handles_empty_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE articles (language TEXT)")
        quality_checks.check_language_values(con, table_name="articles")
    finally:
        con.close()

    assert "No language values found." in capsys.readouterr().out


@pytest.mark.unit
def test_run_all_checks_invokes_all_sections(
    quality_db: duckdb.DuckDBPyConnection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quality_checks.run_all_checks(
        quality_db,
        table_name="articles",
        null_conditions={"title": "title IS NULL OR title = ''"},
        text_columns=["title"],
        language_column="language",
        allowed_languages={"en", "ko"},
        url_column="url",
        duplicate_group_columns=None,
        date_column="published_at",
    )

    output = capsys.readouterr().out
    assert "Total records: 3" in output
    assert "Missing Field Check" in output
    assert "Duplicate URL Check" in output
    assert "Text Length Statistics" in output
    assert "Language Value Check" in output
    assert "Date Check" in output
