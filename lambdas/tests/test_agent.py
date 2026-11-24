import json

import pytest

from common import agent, llm
from common.agent import AnswerTool, run_agent
from common.errors import ModelOutputError, ThrottledError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _validate(data):
    if data.get("ok") is not True:
        raise ValueError("ok must be true")
    return data


ANSWER = AnswerTool("submit_ok", "Submit ok.", SCHEMA, _validate)


def call(name, payload, tid="t1"):
    return {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": payload}}]}


def text(msg):
    return {"role": "assistant", "content": [{"text": msg}]}


def scripted(monkeypatch, replies):
    seen = []
    replies = iter(replies)

    def fake(system, messages, tool_config, **_):
        seen.append({"messages": json.loads(json.dumps(messages)), "tool_config": tool_config})
        reply = next(replies)
        return (reply, "tool_use") if isinstance(reply, dict) else reply

    monkeypatch.setattr(llm, "converse", fake)
    return seen


def test_forces_the_answer_tool_and_stops_on_first_valid_answer(monkeypatch):
    seen = scripted(monkeypatch, [call("submit_ok", {"ok": True})])
    assert run_agent("a", "sys", "user", ANSWER) == {"ok": True}
    assert len(seen) == 1
    config = seen[0]["tool_config"]
    assert config["toolChoice"] == {"tool": {"name": "submit_ok"}}
    assert config["tools"][0]["toolSpec"]["inputSchema"]["json"] == SCHEMA


def test_rejected_answer_is_fed_back_as_an_error_tool_result(monkeypatch):
    seen = scripted(monkeypatch, [call("submit_ok", {"ok": False}, "t1"), call("submit_ok", {"ok": True}, "t2")])
    assert run_agent("a", "sys", "user", ANSWER) == {"ok": True}
    feedback = seen[1]["messages"][-1]["content"][0]["toolResult"]
    assert feedback["toolUseId"] == "t1" and feedback["status"] == "error"
    assert "ok must be true" in feedback["content"][0]["text"]


def test_text_reply_gets_a_nudge(monkeypatch):
    seen = scripted(monkeypatch, [text("hmm"), call("submit_ok", {"ok": True})])
    run_agent("a", "sys", "user", ANSWER)
    assert "calling the submit_ok tool" in seen[1]["messages"][-1]["content"][0]["text"]


def test_unknown_tool_and_truncated_answers_are_rejected(monkeypatch):
    scripted(
        monkeypatch,
        [call("other", {}), (call("submit_ok", {"ok": True}), "max_tokens"), call("submit_ok", {"ok": True})],
    )
    assert run_agent("a", "sys", "user", ANSWER) == {"ok": True}


def test_loop_is_bounded_and_escalates(monkeypatch):
    seen = scripted(monkeypatch, [call("submit_ok", {"ok": False})] * 5)
    with pytest.raises(ModelOutputError):
        run_agent("a", "sys", "user", ANSWER, max_iterations=3)
    assert len(seen) == 3


def test_throttling_is_mapped_to_a_retryable_error(monkeypatch):
    from botocore.exceptions import ClientError

    class Client:
        def converse(self, **_):
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")

    monkeypatch.setattr(llm, "_bedrock", lambda: Client())
    with pytest.raises(ThrottledError):
        agent.run_agent("a", "sys", "user", ANSWER)
