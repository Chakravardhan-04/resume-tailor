"""DynamoDB access. One table, partition key `jobId`, sort key `sk`.

  sk = "META"                      job status record
  sk = "AUDIT#<iso-ts>#<stage>"    one audit entry per stage output
"""

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3

from common import config
from common.guardrails import redact_secrets_deep

META = "META"
MAX_AUDIT_CHARS = 200_000  # stay well below DynamoDB's 400 KB item limit

_table = None


def _tbl():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(config.table_name())
    return _table


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _expires_at() -> int:
    return int(time.time()) + config.record_ttl_seconds()


def create_job(job_id: str, email: str | None = None) -> None:
    item: dict[str, Any] = {
        "jobId": job_id,
        "sk": META,
        "status": "RUNNING",
        "stage": "queued",
        "createdAt": _now(),
        "updatedAt": _now(),
        "expiresAt": _expires_at(),
    }
    if email:
        item["email"] = email  # removed as soon as the email has been attempted
    _tbl().put_item(Item=item, ConditionExpression="attribute_not_exists(jobId)")


def set_email_status(job_id: str, status: str, message: str | None = None) -> None:
    """Record the email outcome and delete the stored address (data minimisation)."""
    _tbl().update_item(
        Key={"jobId": job_id, "sk": META},
        UpdateExpression="SET emailStatus = :s, emailMessage = :m, updatedAt = :u REMOVE email",
        ExpressionAttributeValues={":s": status, ":m": message or "", ":u": _now()},
    )


def set_stage(job_id: str, stage: str) -> None:
    _tbl().update_item(
        Key={"jobId": job_id, "sk": META},
        UpdateExpression="SET stage = :s, updatedAt = :u",
        ExpressionAttributeValues={":s": stage, ":u": _now()},
    )


def mark_done(job_id: str, result: dict[str, Any], result_key: str) -> None:
    _tbl().update_item(
        Key={"jobId": job_id, "sk": META},
        UpdateExpression="SET #st = :d, stage = :s, #r = :r, resultKey = :k, updatedAt = :u",
        ExpressionAttributeNames={"#st": "status", "#r": "result"},
        ExpressionAttributeValues={
            ":d": "DONE",
            ":s": "done",
            ":r": json.loads(json.dumps(result), parse_float=Decimal),
            ":k": result_key,
            ":u": _now(),
        },
    )


def mark_failed(job_id: str, code: str, message: str) -> None:
    _tbl().update_item(
        Key={"jobId": job_id, "sk": META},
        UpdateExpression="SET #st = :f, errorCode = :c, errorMessage = :m, updatedAt = :u",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":f": "FAILED", ":c": code, ":m": message, ":u": _now()},
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    return _tbl().get_item(Key={"jobId": job_id, "sk": META}).get("Item")


def write_audit(job_id: str, stage: str, output: dict[str, Any]) -> None:
    """Persist one stage's output (secrets redacted, size-capped) for the audit trail."""
    payload = json.dumps(redact_secrets_deep(output), default=str)
    if len(payload) > MAX_AUDIT_CHARS:
        payload = payload[:MAX_AUDIT_CHARS] + "...[truncated]"
    ts = _now()
    _tbl().put_item(
        Item={
            "jobId": job_id,
            "sk": f"AUDIT#{ts}#{stage}",
            "stage": stage,
            "timestamp": ts,
            "output": payload,
            "expiresAt": _expires_at(),
        }
    )


def to_plain(value: Any) -> Any:
    """Convert DynamoDB Decimals back to int/float for JSON responses."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    return value
