"""Checks proposed SQL before any database connection receives it."""

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from agent.config import ALLOWED_TABLES

BLOCKED_STATEMENTS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Copy,
    exp.Attach,
    exp.Pragma,
)
BLOCKED_FUNCTIONS = {
    "glob",
    "http_get",
    "http_head",
    "http_post",
    "http_put",
    "http_delete",
    "http_patch",
    "query",
    "query_table",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
}


def _blocked_function_name(function: exp.Func) -> str:
    """Get the SQL function name consistently for named and anonymous nodes."""
    if isinstance(function, exp.Anonymous):
        return function.name.casefold()
    return function.sql_name().casefold()


def _validate_functions(expression: exp.Expression) -> str | None:
    """Reject SQL functions that can read files, use networks, or run SQL."""
    for function in expression.find_all(exp.Func):
        name = _blocked_function_name(function)
        if name in BLOCKED_FUNCTIONS or name.startswith("read_"):
            return f"Function '{name}' is not allowed."
        if name.endswith("_scan"):
            return f"External scan function '{name}' is not allowed."
    return None


def _validate_tables(expression: exp.Expression) -> str | None:
    """Require physical tables to be in the configured allowlist."""
    cte_names = {
        cte.alias_or_name.casefold() for cte in expression.find_all(exp.CTE)
    }
    allowed_tables = {name.casefold() for name in ALLOWED_TABLES}
    for table in expression.find_all(exp.Table):
        if not table.name:
            source = table.this
            if isinstance(source, exp.Func):
                if _blocked_function_name(source) != "generate_series":
                    return "Only the built-in generate_series table function is allowed."
            continue
        name = table.name.casefold()
        if name in cte_names:
            continue
        if table.catalog or table.db not in {"", "main"}:
            return "Catalog and non-main schema references are not allowed."
        if name not in allowed_tables:
            return f"Table '{table.name}' is not allowed."
    return None


def validate(sql: str) -> tuple[bool, str, str | None]:
    """Allow one SELECT; reject writes, unknown tables, and external readers."""
    if not isinstance(sql, str) or not sql.strip():
        return False, "SQL must be a non-empty string.", None
    try:
        statements = parse(sql, read="duckdb")
    except ParseError as error:
        return False, f"SQL could not be parsed: {error}", None
    if len(statements) != 1 or statements[0] is None:
        return False, "Exactly one SQL statement is allowed.", None

    expression = statements[0]
    if not isinstance(expression, exp.Select):
        return False, "Only SELECT statements are allowed.", None
    if any(expression.find(kind) for kind in BLOCKED_STATEMENTS):
        return False, "Write or database configuration statements are not allowed.", None

    function_error = _validate_functions(expression)
    if function_error:
        return False, function_error, None
    table_error = _validate_tables(expression)
    if table_error:
        return False, table_error, None
    return True, "SQL passed validation.", expression.sql(dialect="duckdb")
