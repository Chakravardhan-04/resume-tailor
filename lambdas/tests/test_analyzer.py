import json

import pytest

from analyzer import handler as analyzer
from common import llm, storage
from common.errors import InputError


@pytest.fixture
def fake_jobs(monkeypatch):
    calls = {"stage": [], "audit": [], "failed": []}
    monkeypatch.setattr("common.jobs.set_stage", lambda j, s: calls["stage"].append(s))
    monkeypatch.setattr("common.jobs.write_audit", lambda j, s, o: calls["audit"].append((s, o)))
    monkeypatch.setattr("common.jobs.mark_failed", lambda j, c, m: calls["failed"].append((c, m)))
    return calls


REPLY = json.dumps(
    {
        "requirements": [
            {"id": "x", "text": "Python", "category": "must_have", "type": "skill"},
            {"text": "Kubernetes", "category": "nice_to_have", "type": "bogus"},
        ]
    }
)


def test_validate_requirements_assigns_ids_and_normalizes_type():
    out = analyzer.validate_requirements(json.loads(REPLY))
    assert [r["id"] for r in out["requirements"]] == ["R1", "R2"]
    assert out["requirements"][1]["type"] == "other"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"requirements": []},
        {"requirements": [{"text": "", "category": "must_have"}]},
        {"requirements": [{"text": "x", "category": "weird"}]},
    ],
)
def test_validate_requirements_rejects_bad_shapes(data):
    with pytest.raises(ValueError):
        analyzer.validate_requirements(data)


def test_handler_happy_path_audits_output(monkeypatch, fake_jobs, resume, job):
    monkeypatch.setattr(storage, "read_inputs", lambda _id: (resume, job))
    monkeypatch.setattr(llm, "converse", lambda *a, **k: REPLY)
    out = analyzer.handler({"jobId": "j1"})
    assert len(out["requirements"]) == 2
    assert fake_jobs["stage"] == ["analyzer"]
    assert fake_jobs["audit"][0][0] == "analyzer"


def test_handler_missing_input_fails_with_clear_message(monkeypatch, fake_jobs):
    def boom(_id):
        raise InputError("The resume could not be found for this job.")

    monkeypatch.setattr(storage, "read_inputs", boom)
    with pytest.raises(InputError):
        analyzer.handler({"jobId": "j1"})
    assert fake_jobs["failed"] == [("InputError", "The resume could not be found for this job.")]
    assert fake_jobs["audit"] == []
