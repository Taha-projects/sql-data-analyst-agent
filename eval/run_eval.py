"""Run real-agent evaluations from eval/questions.yaml and save measured CSVs.

YAML format (the project owner writes the question file):

questions:
  - id: orders_count
    question: How many orders are in the dataset?
    gold_sql: SELECT COUNT(*) AS order_count FROM orders
    category: aggregation
    expect: answer
    split: dev

Each item requires a unique string id, question, gold_sql, category, expect,
and split. Expect is answer, refuse, or block; split is dev or test. Answer
items need SELECT gold_sql. Refuse items use an empty gold_sql. Block items
provide SQL that should be rejected by validation or blocked during execution.
The gold SQL is always validated before the executor can run it.
"""

import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
import yaml

load_dotenv()

from agent.agent import AgentResult, answer_question
from agent.executor import execute
from agent.validator import validate
from eval.scoring import score_result

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = PROJECT_ROOT / "eval" / "questions.yaml"
RESULTS_DIRECTORY = PROJECT_ROOT / "eval" / "results"
RESULT_FIELDS = (
    "id", "category", "split", "status", "correct", "attempts",
    "latency_s", "tokens_in", "tokens_out", "cost_usd", "error",
)

ExpectedOutcome = Literal["answer", "refuse", "block"]
EvaluationSplit = Literal["dev", "test"]


@dataclass(frozen=True)
class EvaluationQuestion:
    """Hold one validated item from the hand-written YAML file."""

    id: str
    question: str
    gold_sql: str
    category: str
    expect: ExpectedOutcome
    split: EvaluationSplit


def _parse_question(item: Any, seen_ids: set[str]) -> EvaluationQuestion:
    """Check one YAML item before it can invoke the real agent."""
    required = {"id", "question", "gold_sql", "category", "expect", "split"}
    if not isinstance(item, dict) or set(item) != required:
        raise ValueError(f"Each question must contain exactly: {sorted(required)}")
    if any(not isinstance(item[field], str) for field in required):
        raise ValueError("Every question field must be a string.")
    if not item["id"].strip() or item["id"] in seen_ids:
        raise ValueError(f"Question id is blank or duplicated: {item['id']!r}")
    if item["expect"] not in {"answer", "refuse", "block"}:
        raise ValueError(f"Unsupported expect value for {item['id']}.")
    if item["split"] not in {"dev", "test"}:
        raise ValueError(f"Unsupported split value for {item['id']}.")
    if item["expect"] == "answer" and not item["gold_sql"].strip():
        raise ValueError(f"Answer question {item['id']} needs gold SQL.")
    if item["expect"] == "refuse" and item["gold_sql"].strip():
        raise ValueError(f"Refusal question {item['id']} must have empty gold SQL.")
    if item["expect"] == "block" and not item["gold_sql"].strip():
        raise ValueError(f"Block question {item['id']} needs SQL to block.")
    seen_ids.add(item["id"])
    return EvaluationQuestion(**item)


def load_questions(path: Path = QUESTIONS_PATH) -> list[EvaluationQuestion]:
    """Load trusted, hand-written evaluations without executing YAML objects."""
    with path.open("r", encoding="utf-8") as question_file:
        document = yaml.safe_load(question_file)
    if not isinstance(document, dict) or not isinstance(document.get("questions"), list):
        raise ValueError("questions.yaml must contain a top-level questions list.")
    seen_ids: set[str] = set()
    questions = [_parse_question(item, seen_ids) for item in document["questions"]]
    if not questions:
        raise ValueError("questions.yaml has no evaluation questions yet.")
    return questions


def _run_gold_sql(question: EvaluationQuestion) -> tuple[Any | None, str | None]:
    """Validate the gold query before using the same safe executor as the agent."""
    if question.expect == "refuse":
        return None, None
    try:
        is_valid, reason, cleaned_sql = validate(question.gold_sql)
        if not is_valid or cleaned_sql is None:
            return None, f"Gold SQL was rejected: {reason}"
        return execute(cleaned_sql), None
    except Exception as error:
        return None, f"Gold SQL evaluation failed: {error}"


def _confirm_agent_block(result: AgentResult) -> tuple[bool, str | None]:
    """Confirm a validator rejection or a failed database execution."""
    if result.dataframe is not None:
        return False, None
    for attempt in result.attempts:
        if attempt.stage_failed == "validation" and attempt.sql:
            try:
                is_valid, _, _ = validate(attempt.sql)
            except Exception as error:
                return False, f"Could not confirm validator rejection: {error}"
            if not is_valid:
                return True, None
        if attempt.stage_failed == "execution" and attempt.error_message:
            placeholder_error = "The student will implement SQL execution."
            if attempt.error_message == placeholder_error:
                return False, "Executor is still an unimplemented placeholder."
            return True, None
    return False, None


def _agent_error(result: AgentResult) -> str:
    """Collect recorded attempt errors for the CSV error column."""
    messages = [
        f"Attempt {attempt.number}: {attempt.error_message}"
        for attempt in result.attempts
        if attempt.error_message
    ]
    return " | ".join(messages)


def _evaluate_question(question: EvaluationQuestion) -> dict[str, object]:
    """Run one real agent request, gold query, and outcome comparison."""
    started = time.perf_counter()
    agent_result: AgentResult | None = None
    run_error: str | None = None
    try:
        agent_result = answer_question(question.question)
    except Exception as error:
        run_error = f"Agent run failed: {error}"

    gold_dataframe, gold_error = _run_gold_sql(question)
    confirmed_block = False
    block_error = None
    if agent_result is not None and question.expect == "block":
        confirmed_block, block_error = _confirm_agent_block(agent_result)
    errors = [error for error in (run_error, gold_error, block_error) if error]
    if agent_result is not None:
        attempt_error = _agent_error(agent_result)
        if attempt_error:
            errors.append(attempt_error)
    correct = agent_result is not None and score_result(
        agent_result, question.expect, gold_dataframe, confirmed_block
    )
    return _result_row(
        question, agent_result, correct, started, "; ".join(errors)
    )


def _result_row(
    question: EvaluationQuestion,
    result: AgentResult | None,
    correct: bool,
    started: float,
    error: str,
) -> dict[str, object]:
    """Create the required CSV columns for a completed evaluation item."""
    return {
        "id": question.id,
        "category": question.category,
        "split": question.split,
        "status": result.status if result else "failed",
        "correct": correct,
        "attempts": len(result.attempts) if result else 0,
        "latency_s": result.total_latency_s if result else time.perf_counter() - started,
        "tokens_in": result.tokens_in if result else 0,
        "tokens_out": result.tokens_out if result else 0,
        "cost_usd": result.cost_usd if result else 0.0,
        "error": error,
    }


def _write_results(rows: list[dict[str, object]]) -> Path:
    """Save one actual evaluation run as a separate CSV file."""
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_path = RESULTS_DIRECTORY / f"eval-{timestamp}.csv"
    with output_path.open("w", encoding="utf-8", newline="") as result_file:
        writer = csv.DictWriter(result_file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def _print_summary(rows: list[dict[str, object]]) -> None:
    """Print category and split summaries with test as the final metric."""
    groups: dict[tuple[str, str], list[bool]] = {}
    for row in rows:
        key = (str(row["category"]), str(row["split"]))
        groups.setdefault(key, []).append(bool(row["correct"]))
    for (category, split), outcomes in sorted(groups.items()):
        passed = sum(outcomes)
        label = "development diagnostic" if split == "dev" else "held-out test"
        print(f"{label}: {category} — {passed}/{len(outcomes)} passed")
    test_results = [bool(row["correct"]) for row in rows if row["split"] == "test"]
    if test_results:
        passed = sum(test_results)
        rate = passed / len(test_results) * 100
        print(f"Final held-out test result: {passed}/{len(test_results)} ({rate:.1f}%)")
    else:
        print("No held-out test questions were included; no final score is reported.")


def main() -> None:
    """Run every configured question using the real model and database."""
    questions = load_questions()
    rows = [_evaluate_question(question) for question in questions]
    output_path = _write_results(rows)
    print(f"Saved this run to {output_path}")
    _print_summary(rows)


if __name__ == "__main__":
    main()
