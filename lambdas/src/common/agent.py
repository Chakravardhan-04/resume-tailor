"""The bounded agent loop that every specialist uses.

1. Send the system prompt + documents to Claude, with ONE "answer tool" whose JSON schema
   describes the result. toolChoice forces Claude to answer by calling that tool.
2. Check the answer in code (the tool's validate function).
3. Valid   -> stop and return it.
   Invalid -> send the error back to Claude as a tool result and loop.
4. After MAX_TURNS without a valid answer -> raise ModelOutputError (Step Functions retries the stage).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from common import aws
from common.errors import ModelOutputError

MAX_TURNS = 3  # max iterations per agent loop


@dataclass
class AnswerTool:
    name: str
    description: str
    schema: dict  # JSON schema Claude must follow
    validate: Callable[[dict], dict]  # returns the cleaned answer, or raises ValueError("what is wrong")


def run_agent(agent: str, system: str, user: str, answer: AnswerTool, max_turns: int = MAX_TURNS) -> dict:
    tool_config = {
        "tools": [{"toolSpec": {"name": answer.name, "description": answer.description, "inputSchema": {"json": answer.schema}}}],
        "toolChoice": {"tool": {"name": answer.name}},  # Claude must answer through this tool
    }
    messages = [{"role": "user", "content": [{"text": user}]}]

    for turn in range(1, max_turns + 1):  # bounded: never more than max_turns model calls
        reply, stop_reason = aws.converse(system, messages, tool_config)
        messages.append(reply)
        call = next((block["toolUse"] for block in reply["content"] if "toolUse" in block), None)

        try:
            if call is None:
                raise ValueError(f"answer by calling the {answer.name} tool")
            if stop_reason == "max_tokens":
                raise ValueError("your answer was cut off; give a shorter answer")
            result = answer.validate(call["input"])  # code checks the model's answer
        except ValueError as problem:
            print(f"agent={agent} turn={turn}/{max_turns} rejected: {problem}")
            feedback = (
                {
                    "toolResult": {
                        "toolUseId": call["toolUseId"],
                        "status": "error",
                        "content": [{"text": json.dumps({"error": str(problem)})}],
                    }
                }
                if call
                else {"text": str(problem)}
            )
            messages.append({"role": "user", "content": [feedback]})  # tell Claude exactly what to fix
            continue

        print(f"agent={agent} stop=answer_accepted turns={turn}")
        return result  # stop condition: first valid answer

    print(f"agent={agent} stop=max_turns")
    raise ModelOutputError("The AI did not return a usable answer. Please try again.")
