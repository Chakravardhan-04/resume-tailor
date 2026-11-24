import pytest
from conftest import tool_call

from common import agent, aws
from common.agent import AnswerTool, run_agent
from common.errors import ModelOutputError


def must_be_ok(answer):
    if answer.get("ok") is not True:
        raise ValueError("ok must be true")
    return answer


TOOL = AnswerTool("submit_ok", "Submit.", {"type": "object"}, must_be_ok)


def scripted(monkeypatch, replies):
    calls = []
    replies = iter(replies)
    monkeypatch.setattr(aws, "converse", lambda system, messages, tool_config: calls.append(list(messages)) or next(replies))
    return calls


def test_stops_on_first_valid_answer(monkeypatch):
    calls = scripted(monkeypatch, [tool_call("submit_ok", {"ok": True})])
    assert run_agent("a", "sys", "user", TOOL) == {"ok": True}
    assert len(calls) == 1


def test_invalid_answer_is_sent_back_and_fixed(monkeypatch):
    calls = scripted(monkeypatch, [tool_call("submit_ok", {"ok": False}), tool_call("submit_ok", {"ok": True})])
    assert run_agent("a", "sys", "user", TOOL) == {"ok": True}
    feedback = calls[1][-1]["content"][0]["toolResult"]
    assert feedback["status"] == "error" and "ok must be true" in feedback["content"][0]["text"]


def test_loop_is_bounded_and_escalates(monkeypatch):
    calls = scripted(monkeypatch, [tool_call("submit_ok", {"ok": False})] * 10)
    with pytest.raises(ModelOutputError):
        run_agent("a", "sys", "user", TOOL)
    assert len(calls) == agent.MAX_TURNS == 3
