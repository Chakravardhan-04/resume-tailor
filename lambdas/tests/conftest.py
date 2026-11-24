import os

import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("JOBS_TABLE", "test-table")
os.environ.setdefault("STATE_MACHINE_ARN", "arn:aws:states:us-east-1:123456789012:stateMachine:test")

RESUME = """Jane Doe - Software Engineer with 5 years of experience.
- Built REST APIs in Python and Flask serving 2M requests per day.
- Deployed services to AWS using Lambda and DynamoDB.
- Led a team of 3 engineers on a migration project.
"""


@pytest.fixture
def resume():
    return RESUME


@pytest.fixture
def fake_aws(monkeypatch):
    """Replace every AWS call with an in-memory fake, so unit tests never touch AWS."""
    from common import aws

    state = {"jobs": {}, "audit": [], "files": {}, "emails": []}
    monkeypatch.setattr(aws, "set_stage", lambda j, s: state["jobs"].setdefault(j, {}).update(stage=s))
    monkeypatch.setattr(aws, "write_audit", lambda j, s, o: state["audit"].append((s, o)))
    monkeypatch.setattr(aws, "mark_failed", lambda j, c, m: state["jobs"].setdefault(j, {}).update(status="FAILED", error=m))
    monkeypatch.setattr(aws, "get_text", lambda k: state["files"][k] if k in state["files"] else _missing())
    monkeypatch.setattr(aws, "converse", lambda *a, **k: pytest.fail("unexpected Bedrock call"))
    return state


def _missing():
    from botocore.exceptions import ClientError

    raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")


def tool_call(name, payload, tid="t1"):
    """A fake Bedrock reply in which Claude calls the answer tool."""
    return {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": payload}}]}, "tool_use"
