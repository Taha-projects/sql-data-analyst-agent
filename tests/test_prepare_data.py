"""Checks CSV loading behavior without using the real Olist dataset."""

from pathlib import Path

import duckdb
import pytest

from data.prepare_data import build_database


FAKE_CSVS: tuple[tuple[str, str], ...] = (
    (
        "olist_orders_dataset.csv",
        "order_id,order_purchase_timestamp,order_approved_at,"
        "order_delivered_carrier_date,order_delivered_customer_date,"
        "order_estimated_delivery_date\n"
        "order-1,2018-01-01 10:00:00,2018-01-01 10:05:00,"
        "2018-01-02 10:00:00,2018-01-03 10:00:00,2018-01-05 10:00:00\n",
    ),
    (
        "olist_order_items_dataset.csv",
        "order_id,shipping_limit_date\n"
        "order-1,2018-01-02 10:00:00\n",
    ),
    ("olist_customers_dataset.csv", "customer_id,customer_city\ncustomer-1,Sao Paulo\n"),
    ("olist_products_dataset.csv", "product_id,product_category_name\nproduct-1,books\n"),
    ("olist_order_payments_dataset.csv", "order_id,payment_value\norder-1,12.5\n"),
    (
        "olist_order_reviews_dataset.csv",
        "review_id,review_creation_date,review_answer_timestamp\n"
        "review-1,2018-01-03 10:00:00,2018-01-04 10:00:00\n",
    ),
    ("olist_sellers_dataset.csv", "seller_id,seller_city\nseller-1,Curitiba\n"),
    (
        "olist_geolocation_dataset.csv",
        "geolocation_zip_code_prefix,geolocation_lat\n12345,-25.4\n",
    ),
    (
        "product_category_name_translation.csv",
        "product_category_name,product_category_name_english\nbooks,books\n",
    ),
)

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

DATE_COLUMNS = (
    (
        "orders",
        (
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
    ),
    ("order_items", ("shipping_limit_date",)),
    ("order_reviews", ("review_creation_date", "review_answer_timestamp")),
)


def write_fake_csvs(directory: Path) -> None:
    """Create tiny inputs so tests do not depend on the real dataset."""
    directory.mkdir(parents=True)
    for filename, contents in FAKE_CSVS:
        (directory / filename).write_text(contents, encoding="utf-8")


def assert_table_names_and_order_columns(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Check the table mapping and that CSV column names stay unchanged."""
    table_names = {
        row[0] for row in connection.execute("SHOW TABLES").fetchall()
    }
    assert table_names == set(EXPECTED_TABLES)

    columns = connection.execute('DESCRIBE "orders"').fetchall()
    assert [row[0] for row in columns] == [
        "order_id",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]


def assert_timestamp_columns(connection: duckdb.DuckDBPyConnection) -> None:
    """Check every configured date field is stored as TIMESTAMP."""
    for table_name, date_columns in DATE_COLUMNS:
        schema = {
            row[0]: row[1]
            for row in connection.execute(
                f'DESCRIBE "{table_name}"'
            ).fetchall()
        }
        for column_name in date_columns:
            assert schema[column_name] == "TIMESTAMP"


def assert_one_row_per_table(connection: duckdb.DuckDBPyConnection) -> None:
    """Check rerunning the loader does not duplicate table rows."""
    for table_name in EXPECTED_TABLES:
        count = connection.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).fetchone()[0]
        assert count == 1


def test_build_database_creates_tables_and_reruns_safely(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check tables, timestamps, counts, reruns, printed output, and unchanged CSVs."""
    data_directory = tmp_path / "raw"
    write_fake_csvs(data_directory)
    original_csvs = {
        path.name: path.read_bytes()
        for path in data_directory.glob("*.csv")
    }
    database_path = tmp_path / "retail.duckdb"

    build_database(data_directory, database_path)
    build_database(data_directory, database_path)
    output = capsys.readouterr().out

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        assert_table_names_and_order_columns(connection)
        assert_timestamp_columns(connection)
        assert_one_row_per_table(connection)
    finally:
        connection.close()

    assert "Final column types:" in output
    assert "Table row counts:" in output
    for table_name in EXPECTED_TABLES:
        assert f"  {table_name}: 1" in output
    assert original_csvs == {
        path.name: path.read_bytes()
        for path in data_directory.glob("*.csv")
    }


def test_missing_files_are_listed_before_database_creation(
    tmp_path: Path,
) -> None:
    """Check missing inputs are reported without creating a database."""
    data_directory = tmp_path / "raw"
    data_directory.mkdir()
    database_path = tmp_path / "retail.duckdb"

    with pytest.raises(FileNotFoundError) as error:
        build_database(data_directory, database_path)

    message = str(error.value)
    for filename, _ in FAKE_CSVS:
        assert filename in message
    assert "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce" in message
    assert not database_path.exists()
