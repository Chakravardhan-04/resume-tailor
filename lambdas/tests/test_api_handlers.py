import json
from decimal import Decimal

import pytest

from common import jobs, storage
from status import handler as status
from submit import handler as submit

JOB_ID = "123e4567-e89b-42d3-a456-426614174000"
LONG = "x" * 80
USER = "user-sub-1"
EMAIL = "me@example.com"


def claims(sub=USER, email=EMAIL, verified="true"):
    jwt = {"claims": {"sub": sub, "email": email, "email_verified": verified}}
    return {"requestContext": {"authorizer": {"jwt": jwt}}}


def event(body, **kw):
    return {"body": json.dumps(body), **claims(**kw)}


def status_event(job_id=JOB_ID, **kw):
    return {"pathParameters": {"jobId": job_id}, **claims(**kw)}


class FakeSfn:
    def __init__(self):
        self.started = []

    def start_execution(self, **kwargs):
        self.started.append(kwargs)


@pytest.fixture
def wired(monkeypatch):
    sfn, puts, created = FakeSfn(), {}, []
    monkeypatch.setattr(submit, "_stepfunctions", lambda: sfn)
    monkeypatch.setattr(storage, "put_text", lambda k, t: puts.update({k: t}))
    monkeypatch.setattr(jobs, "create_job", lambda j, e=None, u=None: created.append((j, e, u)))
    monkeypatch.setattr(jobs, "claim_daily_quota", lambda u, limit: True)
    return sfn, puts, created


# ---- submit ----


def test_submit_uses_the_verified_account_email_and_owner(wired):
    sfn, puts, created = wired
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG, "email": "attacker@evil.com"}))
    body = json.loads(res["body"])
    assert res["statusCode"] == 202
    # the body's email is ignored: the recipient is always the authenticated user
    assert created == [(body["jobId"], EMAIL, USER)]
    assert set(puts) == {f"uploads/{body['jobId']}/resume.txt", f"uploads/{body['jobId']}/job.txt"}
    assert json.loads(sfn.started[0]["input"]) == {"jobId": body["jobId"]}
    assert sfn.started[0]["name"] == body["jobId"]


@pytest.mark.parametrize(
    "kw",
    [{"sub": ""}, {"email": ""}, {"verified": "false"}, {"verified": None}],
)
def test_submit_rejects_unverified_or_missing_identity(wired, kw):
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG}, **kw))
    assert res["statusCode"] == 401
    assert not wired[0].started and not wired[2]


def test_submit_without_authorizer_context_is_401(wired):
    res = submit.handler({"body": json.dumps({"resume": LONG, "jobDescription": LONG})})
    assert res["statusCode"] == 401


@pytest.mark.parametrize(
    "body",
    [
        {"resume": LONG},  # missing JD
        {"jobDescription": LONG},  # missing resume
        {"resume": "short", "jobDescription": LONG},
        {"resume": "x" * 15001, "jobDescription": LONG},
    ],
)
def test_submit_rejects_bad_input_without_side_effects(wired, body):
    sfn, puts, created = wired
    res = submit.handler(event(body))
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["error"]
    assert not sfn.started and not puts and not created


def test_submit_rejects_invalid_json(wired):
    assert submit.handler({"body": "{nope", **claims()})["statusCode"] == 400
    assert submit.handler({"body": "[1]", **claims()})["statusCode"] == 400


def test_submit_enforces_daily_quota_before_any_work(wired, monkeypatch):
    monkeypatch.setattr(jobs, "claim_daily_quota", lambda u, limit: False)
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG}))
    assert res["statusCode"] == 429
    assert "tomorrow" in json.loads(res["body"])["error"]
    assert not wired[0].started and not wired[1] and not wired[2]


def test_submit_returns_500_when_start_fails(wired):
    def boom(**_):
        raise RuntimeError("sfn down")

    wired[0].start_execution = boom
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG}))
    assert res["statusCode"] == 500
    assert "sfn down" not in res["body"]


# ---- status ----


def test_status_requires_identity():
    assert status.handler({"pathParameters": {"jobId": JOB_ID}})["statusCode"] == 401


def test_status_validates_job_id():
    assert status.handler(status_event("../etc/passwd"))["statusCode"] == 400
    assert status.handler({**claims()})["statusCode"] == 400


def test_status_not_found(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: None)
    assert status.handler(status_event())["statusCode"] == 404


def test_status_hides_other_users_jobs(monkeypatch):
    item = {"status": "DONE", "userId": "someone-else", "result": {}, "resultKey": "results/x.pdf"}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    res = status.handler(status_event())
    assert res["statusCode"] == 404  # indistinguishable from "does not exist"
    assert "results/x.pdf" not in res["body"]


def test_status_running(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: {"status": "RUNNING", "stage": "scorer", "userId": USER})
    body = json.loads(status.handler(status_event())["body"])
    assert body == {"jobId": JOB_ID, "status": "RUNNING", "stage": "scorer"}


def test_status_done_includes_fresh_download_url(monkeypatch):
    item = {
        "status": "DONE",
        "stage": "done",
        "userId": USER,
        "result": {"score": Decimal("80")},
        "resultKey": "results/x.pdf",
    }
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    monkeypatch.setattr(storage, "presign_pdf", lambda k: f"https://signed/{k}")
    body = json.loads(status.handler(status_event())["body"])
    assert body["result"] == {"score": 80}
    assert body["downloadUrl"] == "https://signed/results/x.pdf"
    assert body["email"] == {"status": "SKIPPED", "message": None}


def test_status_never_returns_the_stored_email_address(monkeypatch):
    item = {"status": "RUNNING", "stage": "scorer", "userId": USER, "email": "secret@example.com"}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    assert "secret@example.com" not in status.handler(status_event())["body"]


def test_status_failed_shows_clear_message(monkeypatch):
    item = {"status": "FAILED", "userId": USER, "errorCode": "InputError", "errorMessage": "The resume is missing."}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    body = json.loads(status.handler(status_event())["body"])
    assert body["error"] == {"code": "InputError", "message": "The resume is missing."}
