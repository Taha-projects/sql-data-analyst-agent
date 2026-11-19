"""Runs validated SQL under fixed read-only database limits."""

from __future__ import annotations

from threading import Timer
from typing import TYPE_CHECKING

import duckdb

from agent.config import DB_PATH, MAX_ROWS, QUERY_TIMEOUT_SECONDS
from agent.validator import validate

if TYPE_CHECKING:
    import pandas


def _limited_query(sql: str) -> str:
    """Wrap validated SQL so the returned table cannot exceed the row cap."""
    query = sql.rstrip().removesuffix(";")
    return f"SELECT * FROM ({query}) AS agent_result LIMIT {MAX_ROWS}"


def execute(sql: str) -> pandas.DataFrame:
    """Use read-only and locked settings so queries cannot change database state."""
    is_valid, reason, cleaned_sql = validate(sql)
    if not is_valid or cleaned_sql is None:
        raise duckdb.InvalidInputException(f"SQL was rejected before execution: {reason}")

    connection = duckdb.connect(
        str(DB_PATH),
        read_only=True,
        config={"enable_external_access": False, "lock_configuration": True},
    )
    timeout = Timer(
        QUERY_TIMEOUT_SECONDS,
        duckdb.interrupt,
        kwargs={"connection": connection},
    )
    timeout.daemon = True
    try:
        timeout.start()
        return connection.execute(_limited_query(cleaned_sql)).fetchdf()
    finally:
        timeout.cancel()
        connection.close()
