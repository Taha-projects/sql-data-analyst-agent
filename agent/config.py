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
