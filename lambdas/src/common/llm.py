"""Bedrock `converse()` client. Authenticates with the Lambda's IAM role; there is no API key."""

import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common import config
from common.errors import ThrottledError

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
            config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, connect_timeout=5, read_timeout=90),
        )
    return _client


def converse(
    system: str,
    messages: list[dict[str, Any]],
    tool_config: dict[str, Any],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> tuple[dict[str, Any], str]:
    """One model turn. Returns (assistant message, stop reason)."""
    try:
        response = _bedrock().converse(
            modelId=config.model_id(),
            system=[{"text": system}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("Bedrock call failed: %s", code)
        if code in _THROTTLE_CODES:
            raise ThrottledError("The AI service is busy. Please retry shortly.") from exc
        raise
    return response["output"]["message"], response.get("stopReason", "")
