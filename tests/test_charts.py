"""Check chart selection using simple dataframe-shaped examples."""

from types import SimpleNamespace

from agent.charts import ChartChoice, choose_chart


def make_frame(columns: list[str], types: dict[str, str]) -> SimpleNamespace:
    """Provide only the dataframe attributes used by the chart rules."""
    return SimpleNamespace(columns=columns, dtypes=types)


def test_category_and_number_choose_bar_chart() -> None:
    # Protects category plus numeric results by choosing a bar chart.
    frame = make_frame(["category", "sales"], {"category": "object", "sales": "int64"})

    assert choose_chart(frame) == ChartChoice("bar", "category", "sales")


def test_date_and_number_choose_line_chart() -> None:
    # Protects date series by choosing a line chart for chronological values.
    frame = make_frame(["month", "revenue"], {"month": "datetime64[ns]", "revenue": "float64"})

    assert choose_chart(frame) == ChartChoice("line", "month", "revenue")


def test_number_then_date_still_chooses_line_chart() -> None:
    # Protects date charts when SQL returns the number column first.
    frame = make_frame(["revenue", "month"], {"revenue": "float64", "month": "date"})

    assert choose_chart(frame) == ChartChoice("line", "month", "revenue")


def test_two_numeric_columns_do_not_guess_a_chart() -> None:
    # Protects ambiguous numeric pairs from arbitrary chart selection.
    frame = make_frame(["min_value", "max_value"], {"min_value": "int64", "max_value": "int64"})

    assert choose_chart(frame) is None


def test_wrong_column_count_does_not_choose_a_chart() -> None:
    # Protects multi-column tables from an unjustified chart guess.
    frame = make_frame(["category", "sales", "orders"], {"category": "object", "sales": "int64", "orders": "int64"})

    assert choose_chart(frame) is None


def test_two_text_columns_do_not_choose_a_chart() -> None:
    # Protects nonnumeric results from being plotted as numeric data.
    frame = make_frame(["city", "state"], {"city": "object", "state": "object"})

    assert choose_chart(frame) is None
