"""Specify the safety behavior required from the SQL executor."""

from pathlib import Path

import duckdb
import pytest

import agent.executor as executor


@pytest.fixture
def configured_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Create a tiny database so tests never touch the project database."""
    database_path = tmp_path / "executor-test.duckdb"
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute("CREATE TABLE orders (order_id INTEGER)")
        connection.executemany(
            "INSERT INTO orders VALUES (?)",
            [(order_id,) for order_id in range(8)],
        )
    finally:
        connection.close()

    monkeypatch.setattr(executor, "DB_PATH", str(database_path), raising=False)
    return database_path


def test_database_connection_rejects_writes(configured_database: Path) -> None:
    # Protects the database from SQL that attempts to insert rows.
    with pytest.raises(duckdb.Error):
        executor.execute("INSERT INTO orders VALUES (8)")


def test_results_are_capped(
    configured_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Protects callers from receiving more than the configured row cap.
    monkeypatch.setattr(executor, "MAX_ROWS", 3, raising=False)

    result = executor.execute("SELECT order_id FROM orders ORDER BY order_id")

    assert len(result.columns) == 1
    assert len(result) == 3
    assert result["order_id"].tolist() == [0, 1, 2]


def test_slow_query_is_stopped_at_timeout(
    configured_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Protects the app from queries that keep running past the allowed time.
    monkeypatch.setattr(
        executor, "QUERY_TIMEOUT_SECONDS", 0.01, raising=False
    )

    with pytest.raises(duckdb.Error):
        executor.execute(
            "SELECT SUM(sin(i)) FROM range(100000000) AS generated(i)"
        )


def test_external_file_reads_are_blocked(
    configured_database: Path,
    tmp_path: Path,
) -> None:
    # Protects local files from being read through a DuckDB table function.
    csv_path = tmp_path / "private.csv"
    csv_path.write_text("secret\nvalue\n", encoding="utf-8")
    query = f"SELECT * FROM read_csv('{csv_path.as_posix()}')"

    with pytest.raises(duckdb.Error):
        executor.execute(query)


def test_sql_cannot_change_connection_configuration(
    configured_database: Path,
) -> None:
    # Protects the executor's locked settings from later SQL changes.
    with pytest.raises(duckdb.Error):
        executor.execute("SET threads = 2")
