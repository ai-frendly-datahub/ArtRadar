from __future__ import annotations

from datetime import date
from pathlib import Path

from artradar.date_storage import (
    apply_date_storage_policy,
    cleanup_date_directories,
    cleanup_dated_reports,
    latest_snapshot_path,
    resolve_read_database_path,
    snapshot_database,
)


def test_snapshot_database_copies_duckdb_to_dated_dir(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "art_data.duckdb"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("db", encoding="utf-8")

    target = snapshot_database(db_path, snapshot_date=date(2026, 3, 13))

    assert target is not None
    assert target == tmp_path / "data" / "snapshots" / "2026-03-13" / "art_data.duckdb"
    assert target.read_text(encoding="utf-8") == "db"


def test_latest_snapshot_path_returns_newest_matching_database(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "art_data.duckdb"
    older = tmp_path / "data" / "snapshots" / "2026-03-12" / "art_data.duckdb"
    newer = tmp_path / "data" / "snapshots" / "2026-03-13" / "art_data.duckdb"
    unrelated = tmp_path / "data" / "snapshots" / "2026-03-14" / "other.duckdb"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    unrelated.parent.mkdir(parents=True)
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    unrelated.write_text("other", encoding="utf-8")

    assert latest_snapshot_path(db_path) == newer


def test_resolve_read_database_path_prefers_primary_database(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "art_data.duckdb"
    snapshot = tmp_path / "data" / "snapshots" / "2026-03-13" / "art_data.duckdb"
    db_path.parent.mkdir(parents=True)
    snapshot.parent.mkdir(parents=True)
    db_path.write_text("primary", encoding="utf-8")
    snapshot.write_text("snapshot", encoding="utf-8")

    assert resolve_read_database_path(db_path) == db_path


def test_resolve_read_database_path_falls_back_to_latest_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "art_data.duckdb"
    snapshot = tmp_path / "data" / "snapshots" / "2026-03-13" / "art_data.duckdb"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("snapshot", encoding="utf-8")

    assert resolve_read_database_path(db_path) == snapshot


def test_cleanup_date_directories_removes_old_folders_only(tmp_path: Path) -> None:
    base_dir = tmp_path / "raw"
    (base_dir / "2026-03-01").mkdir(parents=True)
    (base_dir / "2026-03-12").mkdir(parents=True)
    (base_dir / "misc").mkdir(parents=True)

    removed = cleanup_date_directories(base_dir, keep_days=7, today=date(2026, 3, 13))

    assert removed == 1
    assert not (base_dir / "2026-03-01").exists()
    assert (base_dir / "2026-03-12").exists()
    assert (base_dir / "misc").exists()


def test_cleanup_dated_reports_supports_both_name_patterns(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "art_20260301.html").write_text("old", encoding="utf-8")
    (report_dir / "2026-03-02.html").write_text("old-iso", encoding="utf-8")
    (report_dir / "art_20260312.html").write_text("new", encoding="utf-8")
    (report_dir / "index.html").write_text("index", encoding="utf-8")

    removed = cleanup_dated_reports(report_dir, keep_days=7, today=date(2026, 3, 13))

    assert removed == 2
    assert not (report_dir / "art_20260301.html").exists()
    assert not (report_dir / "2026-03-02.html").exists()
    assert (report_dir / "art_20260312.html").exists()
    assert (report_dir / "index.html").exists()


def test_apply_date_storage_policy_combines_snapshot_and_cleanup(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "art_data.duckdb"
    raw_dir = tmp_path / "data" / "raw"
    report_dir = tmp_path / "reports"
    db_path.parent.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    report_dir.mkdir()
    db_path.write_text("db", encoding="utf-8")
    (raw_dir / "2025-01-01").mkdir()
    (report_dir / "art_20250101.html").write_text("old", encoding="utf-8")

    result = apply_date_storage_policy(
        database_path=db_path,
        raw_data_dir=raw_dir,
        report_dir=report_dir,
        keep_raw_days=30,
        keep_report_days=30,
        snapshot_db=True,
    )

    assert isinstance(result["snapshot_path"], str)
    assert isinstance(result["raw_removed"], int)
    assert isinstance(result["report_removed"], int)
