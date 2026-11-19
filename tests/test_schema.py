"""Checks schema context using a small temporary DuckDB database."""

from pathlib import Path

import duckdb
import pytest

import agent.schema as schema


EXPECTED_TABLES = (
    "orders",
    "order_items",
    "customers",
    "products",
    "order_payments",
    "order_reviews",
    "sellers",
    "geolocation",
    "product_category_translation",
)


def create_test_database(database_path: Path) -> None:
    """Make a tiny database with the tables needed by the schema builder."""
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(
            'CREATE TABLE orders ("sample_text" VARCHAR, "long_sample" VARCHAR)'
        )
        for value in ("alpha", "bravo", "charlie", "delta"):
            connection.execute(
                'INSERT INTO orders VALUES (?, ?)',
                [value, "x" * 50],
            )

        connection.execute(
            'CREATE TABLE order_reviews ('
            '"review_score" INTEGER, '
            '"review_comment_title" VARCHAR, '
            '"review_comment_message" VARCHAR)'
        )
        connection.execute(
            'INSERT INTO order_reviews VALUES (?, ?, ?)',
            [5, "private review title", "private review comment"],
        )

        for table_name in EXPECTED_TABLES:
            if table_name in {"orders", "order_reviews"}:
                continue
            connection.execute(
                f'CREATE TABLE "{table_name}" ("sample_id" INTEGER)'
            )
            connection.execute(f'INSERT INTO "{table_name}" VALUES (1)')
    finally:
        connection.close()


def record_read_only_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> list[bool]:
    """Record connection mode while preserving DuckDB's real connection."""
    original_connect = schema.duckdb.connect
    read_only_flags: list[bool] = []

    def record_connection(
        database: str,
        *,
        read_only: bool = False,
    ) -> duckdb.DuckDBPyConnection:
        """Store the read-only flag passed by the schema builder."""
        read_only_flags.append(read_only)
        return original_connect(database, read_only=read_only)

    monkeypatch.setattr(schema.duckdb, "connect", record_connection)
    return read_only_flags


def test_schema_context_limits_samples_and_omits_review_comments(
    tmp_path: Path,
) -> None:
    """Check the sample cap, truncation, schema names, and comment omission."""
    database_path = tmp_path / "schema.duckdb"
    create_test_database(database_path)
    context = schema.build_schema_context(database_path)

    assert "Table: orders\nRow count: 4" in context
    sample_line = next(
        line for line in context.splitlines() if "sample_text" in line
    )
    samples = sample_line.split("; samples: ", 1)[1].split(", ")
    assert len(samples) == 3

    long_line = next(line for line in context.splitlines() if "long_sample" in line)
    sample_text = long_line.split("; samples: ", 1)[1].split("'")[1]
    assert len(sample_text) == 40

    assert "review_comment_title (VARCHAR; samples omitted)" in context
    assert "review_comment_message (VARCHAR; samples omitted)" in context
    assert "private review title" not in context
    assert "private review comment" not in context
    for relationship in schema.RELATIONSHIPS:
        assert f"- {relationship}" in context


def test_schema_context_opens_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check the schema builder requests a read-only DuckDB connection."""
    database_path = tmp_path / "schema.duckdb"
    create_test_database(database_path)
    read_only_flags = record_read_only_connections(monkeypatch)

    schema.build_schema_context(database_path)

    assert read_only_flags == [True]


def test_schema_context_does_not_cache(tmp_path: Path) -> None:
    """Check a later call sees changes made after the first call."""
    database_path = tmp_path / "schema.duckdb"
    create_test_database(database_path)
    first_context = schema.build_schema_context(database_path)

    writer = duckdb.connect(str(database_path))
    try:
        writer.execute('INSERT INTO orders VALUES (?, ?)', ["echo", "x" * 50])
    finally:
        writer.close()

    second_context = schema.build_schema_context(database_path)
    assert "Table: orders\nRow count: 4" in first_context
    assert "Table: orders\nRow count: 5" in second_context


def test_missing_allowed_tables_are_reported(tmp_path: Path) -> None:
    """Check the builder identifies missing tables in an incomplete database."""
    database_path = tmp_path / "partial.duckdb"
    connection = duckdb.connect(str(database_path))
    connection.close()

    with pytest.raises(ValueError, match="Database is missing allowed table"):
        schema.build_schema_context(database_path)
