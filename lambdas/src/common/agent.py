"""Bounded agent loop on Bedrock tool use.

The model must answer by calling one `answer` tool whose input schema describes the result.
Code validates every call; a rejected call goes back to the model as an error tool result
so it can correct itself. The loop stops on the first accepted answer, or raises
ModelOutputError after `max_iterations` turns (Step Functions then retries or fails the job).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from common import config, llm
from common.errors import ModelOutputError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnswerTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    validate: Callable[[dict[str, Any]], dict[str, Any]]  # returns the cleaned result or raises ValueError

    def spec(self) -> dict[str, Any]:
        return {
            "toolSpec": {"name": self.name, "description": self.description, "inputSchema": {"json": self.input_schema}}
        }


def run_agent(
    agent: str,
    system: str,
    user: str,
    answer: AnswerTool,
    *,
    max_iterations: int | None = None,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    limit = max_iterations or config.max_iterations()
    tool_config = {"tools": [answer.spec()], "toolChoice": {"tool": {"name": answer.name}}}
    messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": user}]}]

    for turn in range(1, limit + 1):
        message, stop_reason = llm.converse(system, messages, tool_config, max_tokens=max_tokens)
        messages.append(message)
        calls = [block["toolUse"] for block in message.get("content", []) if "toolUse" in block]
        if not calls:
            messages.append({"role": "user", "content": [{"text": f"Answer by calling the {answer.name} tool."}]})
            continue

        results = []
        for call in calls:
            try:
                if call.get("name") != answer.name:
                    raise ValueError(f"unknown tool {call.get('name')!r}; call {answer.name}")
                if stop_reason == "max_tokens":
                    raise ValueError("your answer was cut off; give a shorter answer")
                result = answer.validate(call.get("input") or {})
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("agent=%s turn=%d/%d rejected: %s", agent, turn, limit, exc)
                results.append(_tool_result(call["toolUseId"], {"error": str(exc)}, "error"))
                continue
            logger.info("agent=%s stop=answer_accepted turns=%d", agent, turn)
            return result
        messages.append({"role": "user", "content": results})

    logger.warning("agent=%s stop=max_iterations turns=%d", agent, limit)
    raise ModelOutputError("The AI returned an unusable answer. Please try again.")


def _tool_result(tool_use_id: str, payload: dict[str, Any], status: str) -> dict[str, Any]:
    return {"toolResult": {"toolUseId": tool_use_id, "content": [{"text": json.dumps(payload)}], "status": status}}
