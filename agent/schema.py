"""Builds prompt context from a read-only view of the database."""

from pathlib import Path

import duckdb

from agent.config import ALLOWED_TABLES, RELATIONSHIPS


MAX_SAMPLE_VALUES = 3
MAX_SAMPLE_LENGTH = 40
UNTRUSTED_REVIEW_COLUMNS = frozenset(
    {"review_comment_title", "review_comment_message"}
)


def _quote_identifier(name: str) -> str:
    """Quote database names so names are treated as identifiers."""
    return '"' + name.replace('"', '""') + '"'


def _get_table_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> list[tuple[str, str]]:
    """Read column names and types in their original order."""
    rows = connection.execute(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position",
        [table_name],
    ).fetchall()
    return [(column_name, data_type) for column_name, data_type in rows]


def _get_sample_values(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
) -> list[object]:
    """Fetch only a few different non-null values from one column."""
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    query = (
        f"SELECT DISTINCT {quoted_column} FROM {quoted_table} "
        f"WHERE {quoted_column} IS NOT NULL LIMIT {MAX_SAMPLE_VALUES}"
    )
    return [row[0] for row in connection.execute(query).fetchall()]


def _format_sample(value: object) -> str:
    """Shorten each value before displaying it as quoted text."""
    return repr(str(value)[:MAX_SAMPLE_LENGTH])


def _format_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> list[str]:
    """Describe one table without combining values from different rows."""
    quoted_table = _quote_identifier(table_name)
    row_count = connection.execute(
        f"SELECT COUNT(*) FROM {quoted_table}"
    ).fetchone()[0]
    lines = [f"Table: {table_name}", f"Row count: {row_count}", "Columns:"]

    for column_name, column_type in _get_table_columns(connection, table_name):
        if column_name.lower() in UNTRUSTED_REVIEW_COLUMNS:
            lines.append(f"  - {column_name} ({column_type}; samples omitted)")
            continue

        samples = _get_sample_values(connection, table_name, column_name)
        sample_text = ", ".join(_format_sample(value) for value in samples)
        suffix = f"; samples: {sample_text}" if samples else ""
        lines.append(f"  - {column_name} ({column_type}{suffix})")

    return lines


def _validate_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """Stop with a clear error if an allowed table is missing."""
    existing_tables = {
        row[0] for row in connection.execute("SHOW TABLES").fetchall()
    }
    missing_tables = sorted(ALLOWED_TABLES - existing_tables)
    if missing_tables:
        names = ", ".join(missing_tables)
        raise ValueError(f"Database is missing allowed table(s): {names}")


def build_schema_context(db_path: str | Path) -> str:
    """Build fresh prompt context without changing or caching database data."""
    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        _validate_tables(connection)
        lines = ["DATABASE SCHEMA"]

        for table_name in sorted(ALLOWED_TABLES):
            lines.extend(_format_table(connection, table_name))
            lines.append("")

        lines.append("RELATIONSHIPS")
        lines.extend(f"- {relationship}" for relationship in RELATIONSHIPS)
        return "\n".join(lines)
    finally:
        connection.close()
