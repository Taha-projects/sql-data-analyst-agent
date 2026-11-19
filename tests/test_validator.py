"""Specify which SQL statements the validator must accept or reject."""

import pytest

from agent.validator import validate


SQL_CASES = [
    # Protects ordinary SELECT queries from being rejected.
    pytest.param("SELECT order_id FROM orders", True, id="plain-select"),
    # Protects harmless constant queries from being rejected.
    pytest.param("SELECT 1 AS answer", True, id="constant-select"),
    # Protects joins between allowed tables.
    pytest.param("SELECT o.order_id FROM orders AS o JOIN customers AS c ON o.customer_id = c.customer_id", True, id="join"),
    # Protects read-only common table expressions.
    pytest.param("WITH recent AS (SELECT order_id FROM orders) SELECT order_id FROM recent", True, id="cte"),
    # Protects aggregate queries.
    pytest.param("SELECT COUNT(*) AS order_count FROM orders", True, id="aggregate"),
    # Protects read-only subqueries.
    pytest.param("SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM customers)", True, id="subquery"),
    # Protects qualified columns from being mistaken for unsafe SQL.
    pytest.param("SELECT orders.order_id FROM orders", True, id="qualified-column"),
    # Protects DISTINCT queries on allowed data.
    pytest.param("SELECT DISTINCT customer_id FROM orders", True, id="distinct"),
    # Protects one valid statement with a trailing semicolon.
    pytest.param("SELECT order_id FROM orders;", True, id="trailing-semicolon"),
    # Protects valid SQL followed by a harmless comment.
    pytest.param("SELECT order_id FROM orders -- only a comment", True, id="trailing-comment"),
    # Protects semicolons inside string values from being mistaken for extra statements.
    pytest.param("SELECT ';' AS punctuation", True, id="semicolon-in-string"),
    # Protects nested read-only subqueries.
    pytest.param("SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM customers WHERE customer_city = 'x')", True, id="nested-read-only-query"),
    # Blocks table deletion.
    pytest.param("DROP TABLE orders", False, id="drop"),
    # Blocks row deletion.
    pytest.param("DELETE FROM orders", False, id="delete"),
    # Blocks row updates.
    pytest.param("UPDATE orders SET order_status = 'x'", False, id="update"),
    # Blocks row insertion.
    pytest.param("INSERT INTO orders VALUES (1)", False, id="insert"),
    # Blocks table creation.
    pytest.param("CREATE TABLE new_table (id INTEGER)", False, id="create"),
    # Blocks schema changes.
    pytest.param("ALTER TABLE orders ADD COLUMN extra INTEGER", False, id="alter"),
    # Blocks data export and copy operations.
    pytest.param("COPY orders TO 'orders.csv'", False, id="copy"),
    # Blocks attaching another database.
    pytest.param("ATTACH 'other.duckdb' AS other", False, id="attach"),
    # Blocks DuckDB configuration commands.
    pytest.param("PRAGMA version", False, id="pragma"),
    # Blocks two statements in one model response.
    pytest.param("SELECT 1; SELECT 2", False, id="two-statements"),
    # Blocks a write statement after a comment and a valid query.
    pytest.param("SELECT 1; -- harmless comment\nDROP TABLE orders", False, id="write-after-comment"),
    # Blocks uppercase mutation keywords.
    pytest.param("DROP TABLE orders", False, id="uppercase-keyword"),
    # Blocks mixed-case mutation keywords.
    pytest.param("uPdAtE orders SET order_status = 'x'", False, id="mixed-case-keyword"),
    # Blocks writes nested inside a common table expression.
    pytest.param("WITH changed AS (DELETE FROM orders RETURNING *) SELECT * FROM changed", False, id="write-in-cte"),
    # Blocks references to tables outside the allowlist.
    pytest.param("SELECT * FROM secret_table", False, id="unknown-table"),
    # Blocks CSV file-reading table functions.
    pytest.param("SELECT * FROM read_csv('private.csv')", False, id="read-csv"),
    # Blocks automatic CSV file-reading table functions.
    pytest.param("SELECT * FROM read_csv_auto('private.csv')", False, id="read-csv-auto"),
    # Blocks Parquet file-reading table functions.
    pytest.param("SELECT * FROM read_parquet('private.parquet')", False, id="read-parquet"),
    # Blocks JSON file-reading table functions.
    pytest.param("SELECT * FROM read_json('private.json')", False, id="read-json"),
    # Blocks automatic JSON file-reading table functions.
    pytest.param("SELECT * FROM read_json_auto('private.json')", False, id="read-json-auto"),
    # Blocks filesystem globbing.
    pytest.param("SELECT * FROM glob('*.csv')", False, id="glob"),
    # Blocks remote file-reading functions.
    pytest.param("SELECT * FROM read_parquet('https://example.invalid/data.parquet')", False, id="remote-parquet"),
    # Blocks empty input.
    pytest.param("", False, id="empty-string"),
    # Blocks input containing only whitespace.
    pytest.param("   \n\t  ", False, id="whitespace-only"),
    # Blocks natural language that is not SQL.
    pytest.param("Please show me all orders", False, id="non-sql-text"),
    # Blocks a query whose root is not SELECT.
    pytest.param("VALUES (1)", False, id="non-select-root"),
    # Blocks explain commands instead of SELECT queries.
    pytest.param("EXPLAIN SELECT 1", False, id="explain-root"),
    # Blocks views from being created.
    pytest.param("CREATE VIEW order_view AS SELECT * FROM orders", False, id="create-view"),
    # Blocks schema deletion.
    pytest.param("DROP SCHEMA main", False, id="drop-schema"),
    # Blocks database export commands.
    pytest.param("EXPORT DATABASE 'backup'", False, id="export-database"),
    # Blocks access to an unknown schema-qualified table.
    pytest.param("SELECT * FROM other.secret_table", False, id="unknown-qualified-table"),
]


@pytest.mark.parametrize(("sql", "expected_ok"), SQL_CASES)
def test_validate_sql_specification(sql: str, expected_ok: bool) -> None:
    ok, reason, cleaned_sql = validate(sql)

    assert ok is expected_ok
    assert isinstance(reason, str)
    if expected_ok:
        assert cleaned_sql is not None
    else:
        assert cleaned_sql is None
