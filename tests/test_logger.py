"""Check JSONL logging appends useful run data without secret fields."""

import json
from pathlib import Path
from types import SimpleNamespace

from agent.logger import log_question


def make_result(question: str, sql: str) -> SimpleNamespace:
    """Create the result attributes consumed by the logger."""
    attempt = SimpleNamespace(
        number=1,
        sql=sql,
        stage_failed=None,
        error_message=None,
        latency_s=0.25,
    )
    return SimpleNamespace(
        question=question,
        sql=sql,
        status="answered",
        attempts=[attempt],
        total_latency_s=0.3,
        tokens_in=100,
        tokens_out=20,
        cost_usd=0.0,
        api_key="must not be logged",
    )


def test_logger_appends_one_json_line_per_question(tmp_path: Path) -> None:
    # Protects run history by appending separate, parseable JSON records.
    log_path = tmp_path / "runs.jsonl"

    log_question(make_result("Count orders", "SELECT COUNT(*) FROM orders"), log_path)
    log_question(make_result("List customers", "SELECT * FROM customers"), log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 2
    assert records[0]["question"] == "Count orders"
    assert records[1]["sql"] == "SELECT * FROM customers"


def test_logger_records_required_fields_and_no_api_key(tmp_path: Path) -> None:
    # Protects operational visibility while keeping credentials out of logs.
    log_path = tmp_path / "runs.jsonl"
    log_question(make_result("Count orders", "SELECT COUNT(*) FROM orders"), log_path)

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert set(record) == {
        "question", "sql", "status", "attempts", "total_latency_s",
        "tokens_in", "tokens_out", "cost_usd",
    }
    assert record["attempts"][0]["number"] == 1
    assert "api_key" not in record
    assert "must not be logged" not in log_path.read_text(encoding="utf-8")
