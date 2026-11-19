"""Check the agent loop with fake language-model and database dependencies."""

from typing import Any

import pytest

import agent.agent as agent
from agent.llm import LLMCallResult, LLMOutput


@pytest.fixture(autouse=True)
def use_fake_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid opening the real retail database in these workflow tests."""
    monkeypatch.setattr(agent, "build_schema_context", lambda _path: "test schema")


def make_output(
    sql: str = "SELECT 1",
    can_answer: bool = True,
    reason: str = "",
) -> LLMOutput:
    """Create checked model output without calling a language model."""
    return LLMOutput(
        can_answer=can_answer,
        sql=sql,
        assumptions=[],
        reason=reason,
    )


def make_call(
    output: LLMOutput | None,
    error_message: str | None = None,
    tokens_in: int = 1000,
    tokens_out: int = 500,
) -> LLMCallResult:
    """Create a fake model-call result with predictable usage values."""
    return LLMCallResult(output, tokens_in, tokens_out, 0.01, error_message)


def install_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    results: list[LLMCallResult],
) -> list[list[str]]:
    """Return prepared model results and capture retry feedback."""
    pending = iter(results)
    received_errors: list[list[str]] = []

    def fake_generate_sql(
        question: str,
        schema_context: str,
        previous_errors: list[str],
    ) -> LLMCallResult:
        received_errors.append(list(previous_errors))
        return next(pending)

    monkeypatch.setattr(agent, "generate_sql", fake_generate_sql)
    return received_errors


def test_first_try_success_returns_dataframe_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame: Any = {"rows": [1]}
    install_fake_llm(monkeypatch, [make_call(make_output())])
    monkeypatch.setattr(agent, "validate", lambda sql: (True, "", sql))
    monkeypatch.setattr(agent, "execute", lambda sql: frame)
    monkeypatch.setattr(agent, "INPUT_COST_PER_MILLION_TOKENS", 2.0)
    monkeypatch.setattr(agent, "OUTPUT_COST_PER_MILLION_TOKENS", 4.0)

    result = agent.answer_question("Give me an answer")

    assert result.status == "answered"
    assert result.dataframe == frame
    assert len(result.attempts) == 1
    assert result.tokens_in == 1000
    assert result.tokens_out == 500
    assert result.cost_usd == 0.004


def test_third_try_success_feeds_previous_errors_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = install_fake_llm(
        monkeypatch,
        [
            make_call(make_output("unsafe SQL")),
            make_call(make_output("SELECT execution_failure")),
            make_call(make_output("SELECT 1")),
        ],
    )

    def fake_validate(sql: str) -> tuple[bool, str, str | None]:
        if sql == "unsafe SQL":
            return False, "Unsafe query", None
        return True, "", sql

    def fake_execute(sql: str) -> Any:
        if sql == "SELECT execution_failure":
            raise RuntimeError("Database error")
        return {"rows": [1]}

    monkeypatch.setattr(agent, "validate", fake_validate)
    monkeypatch.setattr(agent, "execute", fake_execute)

    result = agent.answer_question("Give me an answer")

    assert result.status == "answered"
    assert [item.stage_failed for item in result.attempts] == [
        "validation", "execution", None
    ]
    assert received == [[], ["Unsafe query"], ["Unsafe query", "Database error"]]


def test_all_execution_attempts_fail_and_are_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_llm(
        monkeypatch,
        [make_call(make_output()) for _ in range(agent.MAX_ATTEMPTS)],
    )
    monkeypatch.setattr(agent, "validate", lambda sql: (True, "", sql))

    def fail_execution(sql: str) -> Any:
        raise RuntimeError("Database is unavailable")

    monkeypatch.setattr(agent, "execute", fail_execution)

    result = agent.answer_question("Give me an answer")

    assert result.status == "failed"
    assert len(result.attempts) == agent.MAX_ATTEMPTS
    assert all(item.stage_failed == "execution" for item in result.attempts)
    assert result.attempts[-1].error_message == "Database is unavailable"


def test_unanswerable_question_returns_refusal_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_llm(
        monkeypatch,
        [make_call(make_output("", can_answer=False, reason="No profit data."))],
    )
    validated_sql: list[str] = []

    def reject_empty_sql(sql: str) -> tuple[bool, str, str | None]:
        validated_sql.append(sql)
        return False, "SQL is empty", None

    monkeypatch.setattr(agent, "validate", reject_empty_sql)
    monkeypatch.setattr(
        agent, "execute", lambda _sql: pytest.fail("Refusal must not execute SQL")
    )

    result = agent.answer_question("What was profit?")

    assert result.status == "refused"
    assert result.answer_text == "No profit data."
    assert validated_sql == [""]
    assert len(result.attempts) == 1


def test_bad_json_is_recorded_and_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = install_fake_llm(
        monkeypatch,
        [
            make_call(None, error_message="Broken JSON"),
            make_call(make_output()),
        ],
    )
    monkeypatch.setattr(agent, "validate", lambda sql: (True, "", sql))
    monkeypatch.setattr(agent, "execute", lambda sql: {"rows": [1]})

    result = agent.answer_question("Give me an answer")

    assert result.status == "answered"
    assert [item.stage_failed for item in result.attempts] == ["json", None]
    assert received == [[], ["Broken JSON"]]


def test_unsafe_sql_is_rejected_before_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_llm(monkeypatch, [make_call(make_output("DROP TABLE orders"))])
    monkeypatch.setattr(agent, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(agent, "validate", lambda _sql: (False, "Unsafe SQL", None))
    monkeypatch.setattr(
        agent, "execute", lambda _sql: pytest.fail("Unsafe SQL reached execute")
    )

    result = agent.answer_question("Delete orders")

    assert result.status == "failed"
    assert result.attempts[0].stage_failed == "validation"
    assert result.dataframe is None
