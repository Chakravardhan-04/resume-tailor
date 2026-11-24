from botocore.exceptions import ClientError

from common import jobs


class FakeTable:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def update_item(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise ClientError({"Error": {"Code": self.error, "Message": "x"}}, "UpdateItem")


def test_claim_quota_is_atomic_and_per_user_per_day(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(jobs, "_tbl", lambda: table)
    assert jobs.claim_daily_quota("u1", 5) is True
    call = table.calls[0]
    assert call["Key"]["jobId"] == "USER#u1" and call["Key"]["sk"].startswith("QUOTA#")
    assert "used < :limit" in call["ConditionExpression"]
    assert call["ExpressionAttributeValues"][":limit"] == 5


def test_claim_quota_returns_false_at_limit(monkeypatch):
    monkeypatch.setattr(jobs, "_tbl", lambda: FakeTable("ConditionalCheckFailedException"))
    assert jobs.claim_daily_quota("u1", 5) is False


def test_claim_quota_propagates_other_errors(monkeypatch):
    import pytest

    monkeypatch.setattr(jobs, "_tbl", lambda: FakeTable("ProvisionedThroughputExceededException"))
    with pytest.raises(ClientError):
        jobs.claim_daily_quota("u1", 5)
