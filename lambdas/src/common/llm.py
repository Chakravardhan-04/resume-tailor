"""Bedrock `converse()` wrapper with a bounded JSON repair loop. No API keys: IAM role only."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common import config
from common.errors import ModelOutputError, ThrottledError

logger = logging.getLogger(__name__)

_THROTTLE_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "TooManyRequestsException",
}

_client = None


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            config=Config(
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=90,
            ),
        )
    return _client


def converse(system: str, messages: list[dict], *, max_tokens: int = 2048, temperature: float = 0.2) -> str:
    """One Bedrock call. `messages` use plain strings: [{"role": "user", "content": "..."}]."""
    try:
        response = _bedrock().converse(
            modelId=config.model_id(),
            system=[{"text": system}],
            messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("Bedrock call failed: %s", code)
        if code in _THROTTLE_CODES:
            raise ThrottledError("The AI service is busy. Please retry shortly.") from exc
        raise
    parts = response["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (tolerates code fences / prose)."""
    cleaned = re.sub(r"```(?:json)?", "", text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model output")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model output is not a JSON object")
    return parsed


def converse_json(
    system: str,
    user: str,
    validate: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    max_tokens: int = 2048,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Call the model until `validate` accepts the reply or the iteration cap is hit.

    `validate` returns the cleaned object or raises ValueError with a message that
    is fed back to the model so it can correct itself.
    """
    limit = max_iterations or config.max_iterations()
    messages = [{"role": "user", "content": user}]
    last_error = "unknown"
    for attempt in range(1, limit + 1):
        reply = converse(system, messages, max_tokens=max_tokens)
        try:
            return validate(extract_json(reply))
        except (ValueError, KeyError, TypeError) as exc:
            last_error = str(exc)
            logger.warning("Model output rejected (attempt %d/%d): %s", attempt, limit, last_error)
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"Your reply was invalid: {last_error}. Reply with ONLY the corrected JSON object.",
                },
            ]
    raise ModelOutputError("The AI returned an unusable answer. Please try again.")
