"""Chooses a simple chart from result column names and data types."""

from dataclasses import dataclass
from typing import Any, Literal


ChartKind = Literal["bar", "line"]


@dataclass(frozen=True)
class ChartChoice:
    """Describe which result columns Streamlit should plot."""

    kind: ChartKind
    x_column: str
    y_column: str


def _type_name(dataframe: Any, column: str) -> str:
    """Read one dtype as text without depending on pandas internals."""
    return str(dataframe.dtypes[column]).lower()


def _is_date_type(type_name: str) -> bool:
    """Recognize common pandas and DuckDB date type names."""
    return "date" in type_name or "time" in type_name


def _is_number_type(type_name: str) -> bool:
    """Recognize numeric types while excluding booleans."""
    numeric_names = (
        "tinyint", "smallint", "integer", "bigint", "hugeint",
        "utinyint", "usmallint", "uinteger", "ubigint", "uhugeint",
        "int", "uint", "float", "double", "decimal",
    )
    return type_name.startswith(numeric_names)


def choose_chart(dataframe: Any) -> ChartChoice | None:
    """Choose a chart only for a single clear category/date and numeric pair."""
    columns = list(dataframe.columns)
    if len(columns) != 2:
        return None

    first, second = columns
    first_type = _type_name(dataframe, first)
    second_type = _type_name(dataframe, second)
    if _is_date_type(first_type) and _is_number_type(second_type):
        return ChartChoice("line", first, second)
    if _is_date_type(second_type) and _is_number_type(first_type):
        return ChartChoice("line", second, first)
    if _is_number_type(first_type) and not _is_number_type(second_type):
        return ChartChoice("bar", second, first)
    if _is_number_type(second_type) and not _is_number_type(first_type):
        return ChartChoice("bar", first, second)
    return None
