"""Calls the language model and checks its JSON response."""

import json
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

load_dotenv()

from agent.config import BASE_URL, LLM_TEMPERATURE, MODEL_NAME
from agent.prompts import build_messages

MAX_NETWORK_RETRIES = 2


class LLMOutput(BaseModel):
    """Check that a model answer has the fields the agent expects."""

    model_config = ConfigDict(extra="forbid", strict=True)

    can_answer: bool
    sql: str
    assumptions: list[str]
    reason: str


@dataclass(frozen=True)
class LLMCallResult:
    """Keep the answer and call measurements together."""

    output: LLMOutput | None
    tokens_in: int
    tokens_out: int
    latency_s: float
    error_message: str | None


def _create_client() -> tuple[OpenAI, str]:
    """Read credentials at runtime and disable hidden SDK retries."""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("LLM_API_KEY is not set.")
    if not BASE_URL:
        raise ValueError("LLM_BASE_URL is not set.")
    if not MODEL_NAME:
        raise ValueError("LLM_MODEL is not set.")

    client = OpenAI(api_key=api_key, base_url=BASE_URL, max_retries=0)
    return client, MODEL_NAME


def _strip_markdown_fence(content: str) -> str:
    """Remove optional code fences before JSON parsing."""
    lines = content.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_output(content: str | None) -> tuple[LLMOutput | None, str | None]:
    """Turn model text into checked data or a useful parsing error."""
    if content is None:
        return None, "The model returned no text."

    try:
        data = json.loads(_strip_markdown_fence(content))
        return LLMOutput.model_validate(data), None
    except (json.JSONDecodeError, ValidationError) as error:
        return None, f"Invalid model JSON: {error}"


def generate_sql(
    question: str,
    schema_context: str,
    previous_errors: list[str],
) -> LLMCallResult:
    """Request JSON once, retrying only temporary connection failures."""
    started = time.perf_counter()
    try:
        client, model = _create_client()
    except ValueError as error:
        return LLMCallResult(None, 0, 0, time.perf_counter() - started, str(error))

    messages = build_messages(question, schema_context, previous_errors)
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=LLM_TEMPERATURE,
            )
            break
        except (APIConnectionError, APITimeoutError) as error:
            if attempt == MAX_NETWORK_RETRIES:
                return LLMCallResult(
                    None, 0, 0, time.perf_counter() - started,
                    f"Network request failed: {error}",
                )

    content = response.choices[0].message.content
    output, error_message = _parse_output(content)
    usage = response.usage
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    return LLMCallResult(
        output, tokens_in, tokens_out, time.perf_counter() - started, error_message
    )
