"""Central configuration values for the SQL Data Analyst Agent."""

import os
from pathlib import Path

MAX_ROWS = 1000
QUERY_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3
LLM_TEMPERATURE = 0
EXPLAIN_MAX_ROWS = 20

DB_PATH = os.getenv("DB_PATH") or str(
    Path(__file__).resolve().parent.parent / "data" / "retail.duckdb"
)
MODEL_NAME = os.getenv("LLM_MODEL")
BASE_URL = os.getenv("LLM_BASE_URL")

ALLOWED_TABLES = frozenset(
    {
        "customers",
        "geolocation",
        "order_items",
        "order_payments",
        "order_reviews",
        "orders",
        "products",
        "sellers",
        "product_category_translation",
    }
)

RELATIONSHIPS: tuple[str, ...] = (
    "orders.customer_id = customers.customer_id",
    "orders.order_id = order_items.order_id",
    "orders.order_id = order_payments.order_id",
    "orders.order_id = order_reviews.order_id",
    "order_items.product_id = products.product_id",
    "order_items.seller_id = sellers.seller_id",
    "products.product_category_name = "
    "product_category_translation.product_category_name",
    "customers.customer_zip_code_prefix = "
    "geolocation.geolocation_zip_code_prefix",
    "sellers.seller_zip_code_prefix = "
    "geolocation.geolocation_zip_code_prefix",
)
