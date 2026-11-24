import json
from decimal import Decimal

import pytest

from common import jobs, storage
from status import handler as status
from submit import handler as submit

JOB_ID = "123e4567-e89b-42d3-a456-426614174000"
LONG = "x" * 80
EMAIL = "me@example.com"


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
    monkeypatch.setattr(jobs, "create_job", lambda j, e=None: created.append((j, e)))
    return sfn, puts, created


def event(body):
    return {"body": json.dumps(body)}


def test_submit_starts_execution(wired):
    sfn, puts, created = wired
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG, "email": " me@example.com "}))
    body = json.loads(res["body"])
    assert res["statusCode"] == 202
    assert created == [(body["jobId"], "me@example.com")]
    assert set(puts) == {f"uploads/{body['jobId']}/resume.txt", f"uploads/{body['jobId']}/job.txt"}
    assert json.loads(sfn.started[0]["input"]) == {"jobId": body["jobId"]}
    assert sfn.started[0]["name"] == body["jobId"]


@pytest.mark.parametrize(
    "body",
    [
        {"resume": LONG, "email": EMAIL},  # missing JD
        {"jobDescription": LONG, "email": EMAIL},  # missing resume
        {"resume": "short", "jobDescription": LONG, "email": EMAIL},
        {"resume": "x" * 15001, "jobDescription": LONG, "email": EMAIL},
        {"resume": LONG, "jobDescription": LONG},  # missing email
        {"resume": LONG, "jobDescription": LONG, "email": "not-an-email"},
        {"resume": LONG, "jobDescription": LONG, "email": "a@b.com\r\nBcc: x@y.com"},
    ],
)
def test_submit_rejects_bad_input_without_side_effects(wired, body):
    sfn, puts, created = wired
    res = submit.handler(event(body))
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["error"]
    assert not sfn.started and not puts and not created


def test_submit_rejects_invalid_json(wired):
    assert submit.handler({"body": "{nope"})["statusCode"] == 400
    assert submit.handler({"body": "[1]"})["statusCode"] == 400


def test_submit_returns_500_when_start_fails(wired, monkeypatch):
    def boom(**_):
        raise RuntimeError("sfn down")

    wired[0].start_execution = boom
    res = submit.handler(event({"resume": LONG, "jobDescription": LONG, "email": EMAIL}))
    assert res["statusCode"] == 500
    assert "sfn down" not in res["body"]


def test_status_validates_job_id():
    assert status.handler({"pathParameters": {"jobId": "../etc/passwd"}})["statusCode"] == 400
    assert status.handler({})["statusCode"] == 400


def test_status_not_found(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: None)
    assert status.handler({"pathParameters": {"jobId": JOB_ID}})["statusCode"] == 404


def test_status_running(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: {"status": "RUNNING", "stage": "scorer"})
    body = json.loads(status.handler({"pathParameters": {"jobId": JOB_ID}})["body"])
    assert body == {"jobId": JOB_ID, "status": "RUNNING", "stage": "scorer"}


def test_status_done_includes_fresh_download_url(monkeypatch):
    item = {"status": "DONE", "stage": "done", "result": {"score": Decimal("80")}, "resultKey": "results/x.pdf"}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    monkeypatch.setattr(storage, "presign_pdf", lambda k: f"https://signed/{k}")
    body = json.loads(status.handler({"pathParameters": {"jobId": JOB_ID}})["body"])
    assert body["result"] == {"score": 80}
    assert body["downloadUrl"] == "https://signed/results/x.pdf"
    assert body["email"] == {"status": "SKIPPED", "message": None}


def test_status_never_returns_the_stored_email_address(monkeypatch):
    item = {"status": "RUNNING", "stage": "scorer", "email": "secret@example.com"}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    assert "secret@example.com" not in status.handler({"pathParameters": {"jobId": JOB_ID}})["body"]


def test_status_failed_shows_clear_message(monkeypatch):
    item = {"status": "FAILED", "errorCode": "InputError", "errorMessage": "The resume is missing."}
    monkeypatch.setattr(jobs, "get_job", lambda _id: item)
    body = json.loads(status.handler({"pathParameters": {"jobId": JOB_ID}})["body"])
    assert body["error"] == {"code": "InputError", "message": "The resume is missing."}
