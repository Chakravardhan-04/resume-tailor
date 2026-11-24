import pytest

from analyzer import handler as analyzer
from common import tools
from common.errors import InputError
from scorer import handler as scorer

EVENT = {"jobId": "j1", "inputs": {"resume_key": "uploads/j1/resume.txt", "job_key": "uploads/j1/job.txt"}}


@pytest.fixture
def fake_jobs(monkeypatch):
    calls = {"stage": [], "audit": [], "failed": []}
    monkeypatch.setattr("common.jobs.set_stage", lambda j, s: calls["stage"].append(s))
    monkeypatch.setattr("common.jobs.write_audit", lambda j, s, o: calls["audit"].append((s, o)))
    monkeypatch.setattr("common.jobs.mark_failed", lambda j, c, m: calls["failed"].append((c, m)))
    return calls


def test_analyzer_reads_inputs_from_state_and_audits_output(monkeypatch, fake_jobs, resume, job):
    seen = {}
    monkeypatch.setattr(tools, "read_inputs", lambda **k: seen.update(k) or {"resume_text": resume, "job_text": job})
    monkeypatch.setattr(tools, "extract_requirements", lambda job_text: {"requirements": [{"id": "R1"}]})
    out = analyzer.handler(EVENT)
    assert seen == EVENT["inputs"]
    assert out == {"requirements": [{"id": "R1"}]}
    assert fake_jobs["stage"] == ["analyzer"]
    assert fake_jobs["audit"] == [("analyzer", out)]


def test_scorer_uses_analysis_from_state(monkeypatch, fake_jobs, resume, job):
    monkeypatch.setattr(tools, "read_inputs", lambda **k: {"resume_text": resume, "job_text": job})
    monkeypatch.setattr(
        tools, "score_match", lambda resume_text, requirements: {"score": len(requirements), "matched": [], "gaps": []}
    )
    out = scorer.handler({**EVENT, "analysis": {"requirements": [{"id": "R1"}, {"id": "R2"}]}})
    assert out["score"] == 2
    assert fake_jobs["audit"][0][0] == "scorer"


def test_missing_input_fails_the_job_with_a_clear_message(monkeypatch, fake_jobs):
    def missing(**_):
        raise InputError("The job description is missing for this job.")

    monkeypatch.setattr(tools, "read_inputs", missing)
    with pytest.raises(InputError):
        analyzer.handler(EVENT)
    assert fake_jobs["failed"] == [("InputError", "The job description is missing for this job.")]
    assert fake_jobs["audit"] == []


def test_state_without_keys_escalates(fake_jobs):
    with pytest.raises(InputError, match="resume_key"):
        analyzer.handler({"jobId": "j1"})
    assert fake_jobs["failed"][0][0] == "InputError"
