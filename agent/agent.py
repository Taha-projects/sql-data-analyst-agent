"""Coordinates schema, SQL generation, validation, and query execution."""

import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent.config import (
    DB_PATH,
    INPUT_COST_PER_MILLION_TOKENS,
    MAX_ATTEMPTS,
    OUTPUT_COST_PER_MILLION_TOKENS,
    TOKENS_PER_MILLION,
)
from agent.executor import execute
from agent.llm import LLMCallResult, LLMOutput, generate_sql
from agent.schema import build_schema_context
from agent.validator import validate

FailureStage = Literal["json", "validation", "execution"]
ResultStatus = Literal["answered", "refused", "failed"]


class Attempt(BaseModel):
    """Record one generation and execution attempt for later review."""

    model_config = ConfigDict(extra="forbid")

    number: int
    sql: str
    stage_failed: FailureStage | None
    error_message: str | None
    latency_s: float


class AgentResult(BaseModel):
    """Return the answer and its complete attempt history to the caller."""

    model_config = ConfigDict(extra="forbid")

    status: ResultStatus
    question: str
    sql: str
    dataframe: Any | None
    answer_text: str
    assumptions: list[str]
    attempts: list[Attempt]
    total_latency_s: float
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class _CandidateOutcome:
    """Carry one validated candidate through the attempt loop."""

    attempt: Attempt
    status: Literal["answered", "refused"] | None
    sql: str
    dataframe: Any | None
    answer_text: str
    assumptions: list[str]
    retry_error: str | None


def _error_text(error: Exception) -> str:
    """Keep a useful failure message even for exceptions with empty text."""
    return str(error).strip() or type(error).__name__


def _make_attempt(
    number: int,
    sql: str,
    stage: FailureStage | None,
    error_message: str | None,
    started: float,
) -> Attempt:
    """Build a consistent record for every completed attempt."""
    return Attempt(
        number=number,
        sql=sql,
        stage_failed=stage,
        error_message=error_message,
        latency_s=time.perf_counter() - started,
    )


def _failure_outcome(
    number: int,
    output: LLMOutput,
    stage: FailureStage,
    error_message: str,
    started: float,
    status: Literal["refused"] | None = None,
    attempt_sql: str | None = None,
) -> _CandidateOutcome:
    """Record a validation or execution failure for a later retry."""
    failed_sql = output.sql if attempt_sql is None else attempt_sql
    return _CandidateOutcome(
        attempt=_make_attempt(number, failed_sql, stage, error_message, started),
        status=status,
        sql=failed_sql,
        dataframe=None,
        answer_text=output.reason if status == "refused" else error_message,
        assumptions=output.assumptions,
        retry_error=error_message,
    )


def _success_outcome(
    number: int,
    output: LLMOutput,
    sql: str,
    dataframe: Any,
    started: float,
) -> _CandidateOutcome:
    """Record a successfully validated and executed query."""
    attempt = _make_attempt(number, sql, None, None, started)
    return _CandidateOutcome(
        attempt, "answered", sql, dataframe,
        "Query executed successfully.", output.assumptions, None,
    )


def _process_candidate(
    number: int,
    output: LLMOutput,
    started: float,
) -> _CandidateOutcome:
    """Validate every parsed SQL candidate before considering execution."""
    try:
        is_valid, reason, cleaned_sql = validate(output.sql)
    except Exception as error:
        refused = "refused" if not output.can_answer else None
        return _failure_outcome(
            number, output, "validation", _error_text(error), started, refused
        )

    if not output.can_answer:
        attempt = _make_attempt(number, output.sql, None, None, started)
        return _CandidateOutcome(
            attempt, "refused", output.sql, None, output.reason,
            output.assumptions, None,
        )

    if not is_valid or cleaned_sql is None:
        message = reason or "Validator rejected SQL or returned no cleaned SQL."
        return _failure_outcome(number, output, "validation", message, started)

    try:
        dataframe = execute(cleaned_sql)
    except Exception as error:
        return _failure_outcome(
            number,
            output,
            "execution",
            _error_text(error),
            started,
            attempt_sql=cleaned_sql,
        )

    return _success_outcome(number, output, cleaned_sql, dataframe, started)


def _call_model(
    question: str,
    schema_context: str,
    previous_errors: list[str],
) -> LLMCallResult:
    """Turn unexpected model-call exceptions into recorded JSON failures."""
    started = time.perf_counter()
    try:
        return generate_sql(question, schema_context, previous_errors)
    except Exception as error:
        return LLMCallResult(
            None, 0, 0, time.perf_counter() - started, _error_text(error)
        )


def _calculate_cost(tokens_in: int, tokens_out: int) -> float:
    """Estimate cost from the configured per-million-token prices."""
    input_cost = tokens_in * INPUT_COST_PER_MILLION_TOKENS
    output_cost = tokens_out * OUTPUT_COST_PER_MILLION_TOKENS
    return (input_cost + output_cost) / TOKENS_PER_MILLION


def _build_result(
    status: ResultStatus,
    question: str,
    sql: str,
    dataframe: Any | None,
    answer_text: str,
    assumptions: list[str],
    attempts: list[Attempt],
    started: float,
    tokens_in: int,
    tokens_out: int,
) -> AgentResult:
    """Assemble the same complete result shape for every final status."""
    return AgentResult(
        status=status,
        question=question,
        sql=sql,
        dataframe=dataframe,
        answer_text=answer_text,
        assumptions=assumptions,
        attempts=attempts,
        total_latency_s=time.perf_counter() - started,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=_calculate_cost(tokens_in, tokens_out),
    )


def _record_json_failure(
    number: int,
    model_result: LLMCallResult,
    started: float,
    attempts: list[Attempt],
    previous_errors: list[str],
) -> None:
    """Record a missing or invalid model response before retrying."""
    message = model_result.error_message or "Model returned no valid JSON."
    attempts.append(_make_attempt(number, "", "json", message, started))
    previous_errors.append(message)


def _failed_result(
    question: str,
    attempts: list[Attempt],
    assumptions: list[str],
    started: float,
    tokens_in: int,
    tokens_out: int,
) -> AgentResult:
    """Return the last recorded error after retries are exhausted."""
    last_attempt = attempts[-1]
    message = last_attempt.error_message or "No valid query was executed."
    return _build_result(
        "failed", question, last_attempt.sql, None, message, assumptions,
        attempts, started, tokens_in, tokens_out,
    )


def answer_question(question: str) -> AgentResult:
    """Run bounded retries while recording failures and validating SQL."""
    started = time.perf_counter()
    schema_context = build_schema_context(DB_PATH)
    attempts: list[Attempt] = []
    previous_errors: list[str] = []
    tokens_in = 0
    tokens_out = 0
    last_assumptions: list[str] = []
    for number in range(1, MAX_ATTEMPTS + 1):
        attempt_started = time.perf_counter()
        model_result = _call_model(question, schema_context, previous_errors)
        tokens_in += model_result.tokens_in
        tokens_out += model_result.tokens_out
        output = model_result.output
        if output is None:
            _record_json_failure(
                number, model_result, attempt_started, attempts, previous_errors
            )
            continue

        last_assumptions = output.assumptions
        outcome = _process_candidate(number, output, attempt_started)
        attempts.append(outcome.attempt)
        if outcome.retry_error:
            previous_errors.append(outcome.retry_error)
        if outcome.status is not None:
            return _build_result(
                outcome.status, question, outcome.sql, outcome.dataframe,
                outcome.answer_text, outcome.assumptions, attempts, started,
                tokens_in, tokens_out,
            )

    return _failed_result(
        question, attempts, last_assumptions, started, tokens_in, tokens_out
    )
