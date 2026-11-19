"""Appends question summaries without recording credentials or headers."""

import json
from pathlib import Path
from typing import Any


RUN_LOG_PATH = Path(__file__).resolve().parent.parent / "runs.jsonl"


def _attempt_records(attempts: list[Any]) -> list[dict[str, object]]:
    """Keep each attempt's stage and error for later debugging."""
    return [
        {
            "number": attempt.number,
            "sql": attempt.sql,
            "stage_failed": attempt.stage_failed,
            "error_message": attempt.error_message,
            "latency_s": attempt.latency_s,
        }
        for attempt in attempts
    ]


def _run_record(result: Any) -> dict[str, object]:
    """Select only the explicitly approved non-secret run fields."""
    return {
        "question": result.question,
        "sql": result.sql,
        "status": result.status,
        "attempts": _attempt_records(result.attempts),
        "total_latency_s": result.total_latency_s,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
    }


def log_question(result: Any, log_path: str | Path = RUN_LOG_PATH) -> None:
    """Append one JSON record per question without including API secrets."""
    record = _run_record(result)
    with Path(log_path).open("a", encoding="utf-8", newline="\n") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
