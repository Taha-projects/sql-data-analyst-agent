"""Check LLM prompts and response handling without making API calls."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import APIConnectionError

import agent.llm as llm
from agent.prompts import build_messages


def make_response(content: str) -> SimpleNamespace:
    """Create the small response shape used by the caller."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content))
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
    )


class FakeClient:
    """Return prepared responses or raise prepared network errors."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )

    def create(self, **kwargs: object) -> object:
        """Record a request and return the next prepared outcome."""
        self.calls.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_build_messages_includes_rules_schema_question_and_errors() -> None:
    messages = build_messages("Count orders", "Table: orders", ["bad column"])

    assert messages[0]["role"] == "system"
    assert "Return only valid JSON" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Table: orders" in messages[1]["content"]
    assert "Count orders" in messages[1]["content"]
    assert "bad column" in messages[1]["content"]


def test_generate_sql_parses_fenced_json_and_counts_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient([
        make_response(
            '```json\n{"can_answer":true,"sql":"SELECT 1",'
            '"assumptions":[],"reason":""}\n```'
        )
    ])
    monkeypatch.setattr(llm, "_create_client", lambda: (client, "test-model"))

    result = llm.generate_sql("Question", "Schema", [])

    assert result.output is not None
    assert result.output.sql == "SELECT 1"
    assert result.tokens_in == 12
    assert result.tokens_out == 7
    assert result.error_message is None
    assert len(client.calls) == 1


def test_generate_sql_returns_error_for_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient([make_response("not JSON")])
    monkeypatch.setattr(llm, "_create_client", lambda: (client, "test-model"))

    result = llm.generate_sql("Question", "Schema", [])

    assert result.output is None
    assert result.error_message is not None
    assert len(client.calls) == 1


def test_generate_sql_retries_network_error_at_most_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_error = APIConnectionError(
        message="temporary network failure",
        request=Mock(),
    )
    client = FakeClient([
        network_error,
        network_error,
        make_response(
            '{"can_answer":true,"sql":"SELECT 1",'
            '"assumptions":[],"reason":""}'
        ),
    ])
    monkeypatch.setattr(llm, "_create_client", lambda: (client, "test-model"))

    result = llm.generate_sql("Question", "Schema", [])

    assert result.output is not None
    assert len(client.calls) == 3
