import pytest

from common import llm
from common.errors import ModelOutputError


def test_extract_json_handles_fences_and_prose():
    text = 'Here you go:\n```json\n{"a": 1, "b": [2]}\n```\nThanks'
    assert llm.extract_json(text) == {"a": 1, "b": [2]}


def test_extract_json_raises_without_object():
    with pytest.raises(ValueError):
        llm.extract_json("no json here")


def _validator(data):
    if "ok" not in data:
        raise ValueError("missing ok")
    return data


def test_converse_json_retries_then_succeeds(monkeypatch):
    replies = iter(["not json", '{"nope": 1}', '{"ok": true}'])
    seen = []

    def fake_converse(system, messages, **_):
        seen.append(len(messages))
        return next(replies)

    monkeypatch.setattr(llm, "converse", fake_converse)
    assert llm.converse_json("sys", "user", _validator, max_iterations=3) == {"ok": True}
    assert seen == [1, 3, 5]  # corrective feedback accumulates


def test_converse_json_is_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "converse", lambda *a, **k: calls.append(1) or "garbage")
    with pytest.raises(ModelOutputError):
        llm.converse_json("sys", "user", _validator, max_iterations=2)
    assert len(calls) == 2
