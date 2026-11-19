"""Builds the local DuckDB database from the Olist CSV files."""

from pathlib import Path

import duckdb

from agent.config import DB_PATH


DATA_DIRECTORY = Path(__file__).resolve().parent / "raw"
DOWNLOAD_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"

TABLE_FILES: dict[str, str] = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_translation": "product_category_name_translation.csv",
}

DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "orders": (
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ),
    "order_items": ("shipping_limit_date",),
    "order_reviews": ("review_creation_date", "review_answer_timestamp"),
}


def find_missing_files(data_directory: Path) -> list[Path]:
    """Find all required files before opening the database, so missing data changes nothing."""
    return [
        data_directory / filename
        for filename in TABLE_FILES.values()
        if not (data_directory / filename).is_file()
    ]


def convert_date_columns(
    relation: duckdb.DuckDBPyRelation,
    table_name: str,
) -> duckdb.DuckDBPyRelation:
    """Cast known date columns explicitly while keeping their original names and order."""
    date_columns = DATE_COLUMNS.get(table_name, ())
    missing_columns = [name for name in date_columns if name not in relation.columns]
    if missing_columns:
        names = ", ".join(missing_columns)
        raise ValueError(f"{table_name} is missing expected date column(s): {names}")

    if not date_columns:
        return relation

    replacements = ", ".join(
        f'CAST("{name}" AS TIMESTAMP) AS "{name}"'
        for name in date_columns
    )
    return relation.select(f"* REPLACE ({replacements})")

def create_tables(
    connection: duckdb.DuckDBPyConnection,
    data_directory: Path,
) -> None:
    """Create or replace each dataset table within the caller's transaction."""
    for table_name, filename in TABLE_FILES.items():
        csv_path = data_directory / filename
        relation = connection.read_csv(csv_path, header=True)
        relation = convert_date_columns(relation, table_name)
        create_table_sql = (
            f'CREATE OR REPLACE TABLE "{table_name}" '
            f"AS {relation.sql_query()}"
        )
        connection.execute(create_table_sql)

def print_final_column_types(connection: duckdb.DuckDBPyConnection) -> None:
    """Show inferred and explicitly converted types, so the resulting schema is visible."""
    print("Final column types:")
    for table_name in TABLE_FILES:
        columns = connection.execute(f'DESCRIBE "{table_name}"').fetchall()
        print(f"\n{table_name}:")
        for column_name, column_type, *_ in columns:
            print(f"  {column_name}: {column_type}")


def print_table_row_counts(connection: duckdb.DuckDBPyConnection) -> None:
    """Report every table's size after all tables have been created."""
    print("\nTable row counts:")
    for table_name in TABLE_FILES:
        count = connection.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).fetchone()[0]
        print(f"  {table_name}: {count:,}")


def build_database(
    data_directory: Path = DATA_DIRECTORY,
    database_path: str | Path = DB_PATH,
) -> None:
    """Replace the nine dataset tables in one transaction, making reruns predictable."""
    missing_files = find_missing_files(data_directory)
    if missing_files:
        missing_names = "\n".join(f"  - {path.name}" for path in missing_files)
        raise FileNotFoundError(
            f"Missing required Olist CSV files in {data_directory}:\n"
            f"{missing_names}\n"
            f"Download the Brazilian E-Commerce Public Dataset by Olist from:\n"
            f"{DOWNLOAD_URL}\n"
            f"Extract the CSV files into {data_directory}."
        )

    output_path = Path(database_path)
    if output_path.resolve() in {path.resolve() for path in data_directory.glob("*.csv")}:
        raise ValueError("The DuckDB output path must not point to an input CSV file.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(output_path))
    try:
        connection.begin()
        try:
            create_tables(connection, data_directory)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        print_final_column_types(connection)
        print_table_row_counts(connection)
    finally:
        connection.close()


def main() -> None:
    """Print a clean missing-file message instead of a traceback for this common setup issue."""
    try:
        build_database()
    except FileNotFoundError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
