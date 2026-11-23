import os

import pytest

# Defaults so config accessors work without a deployed stack.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("DATA_BUCKET", "test-bucket")
os.environ.setdefault("JOBS_TABLE", "test-table")
os.environ.setdefault("STATE_MACHINE_ARN", "arn:aws:states:us-east-1:123456789012:stateMachine:test")


RESUME = """Jane Doe
Software Engineer with 5 years of experience.
- Built REST APIs in Python and Flask serving 2M requests per day.
- Deployed services to AWS using Lambda and DynamoDB.
- Led a team of 3 engineers on a migration project.
"""

JOB = """We are hiring a Backend Engineer.
Must have: Python, AWS Lambda, 3+ years of experience.
Nice to have: Kubernetes, Terraform.
"""


@pytest.fixture(autouse=True)
def block_aws(monkeypatch):
    """Unit tests must never reach real AWS, even if the machine has credentials."""

    def blocked(*_a, **_k):
        raise RuntimeError("AWS call attempted in a unit test; patch the function under test")

    monkeypatch.setattr("common.jobs._tbl", blocked)
    monkeypatch.setattr("common.storage._client", blocked)
    monkeypatch.setattr("common.llm._bedrock", blocked)


@pytest.fixture
def resume():
    return RESUME


@pytest.fixture
def job():
    return JOB
