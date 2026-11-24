import json

from analyzer import handler as analyzer
from common import aws
from submit import handler as submit

CLAIMS = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": "u1", "email": "me@example.com", "email_verified": "true"}}}}}
LONG = "x" * 80


def test_submit_rejects_long_input_and_starts_nothing(monkeypatch):
    started = []
    monkeypatch.setattr(submit.stepfunctions, "start_execution", lambda **k: started.append(k))
    event = {"body": json.dumps({"resume": "x" * 15_001, "jobDescription": LONG}), **CLAIMS}
    res = submit.handler(event)
    assert res["statusCode"] == 400 and "too long" in res["body"] and not started


def test_submit_starts_the_pipeline_with_keys_in_the_state(monkeypatch):
    started, stored = [], {}
    monkeypatch.setattr(submit.stepfunctions, "start_execution", lambda **k: started.append(k))
    monkeypatch.setattr(aws, "claim_daily_quota", lambda u: True)
    monkeypatch.setattr(aws, "put_text", lambda k, t: stored.update({k: t}))
    monkeypatch.setattr(aws, "create_job", lambda j, u, e: None)
    res = submit.handler({"body": json.dumps({"resume": LONG, "jobDescription": LONG}), **CLAIMS})
    job_id = json.loads(res["body"])["jobId"]
    assert res["statusCode"] == 202
    assert json.loads(started[0]["input"]) == {
        "jobId": job_id,
        "inputs": {"resume_key": f"uploads/{job_id}/resume.txt", "job_key": f"uploads/{job_id}/job.txt"},
    }


def test_stage_failure_is_recorded_for_the_user(fake_aws):
    """Forced failure: only the resume exists, so read_inputs raises and the job gets a clear message."""
    import pytest

    from common.errors import InputError

    fake_aws["files"]["uploads/j1/resume.txt"] = LONG
    with pytest.raises(InputError):  # Step Functions Catch takes over from here
        analyzer.handler({"jobId": "j1", "inputs": {"resume_key": "uploads/j1/resume.txt", "job_key": "uploads/j1/job.txt"}})
    assert fake_aws["jobs"]["j1"]["status"] == "FAILED"
    assert "job description is missing" in fake_aws["jobs"]["j1"]["error"]
    assert fake_aws["audit"] == []


def test_email_is_sent_only_when_the_user_asks(monkeypatch):
    from status import handler as status

    job = {
        "userId": "u1",
        "status": "DONE",
        "email": "me@example.com",
        "resultKey": "results/j1.pdf",
        "result": {"score": 80, "summary": "s", "bullets": ["b"], "gaps": []},
    }
    sent, updates = [], []
    monkeypatch.setattr(aws, "get_job", lambda j: job)
    monkeypatch.setattr(aws, "get_pdf", lambda k: b"%PDF")
    monkeypatch.setattr(aws, "send_email", lambda to, r, p: sent.append(to) or ("SENT", ""))
    monkeypatch.setattr(aws, "table", type("T", (), {"update_item": lambda self, **k: updates.append(k)})())

    post = {"pathParameters": {"jobId": "j1"}, **CLAIMS}
    post["requestContext"] = {**CLAIMS["requestContext"], "http": {"method": "POST"}}
    res = status.handler(post)

    assert res["statusCode"] == 200 and sent == ["me@example.com"]
    assert "REMOVE email" in updates[0]["UpdateExpression"]  # address deleted after sending

    other = {**post, "requestContext": {"http": {"method": "POST"}, "authorizer": {"jwt": {"claims": {"sub": "u2"}}}}}
    assert status.handler(other)["statusCode"] == 404  # cannot email someone else's job
