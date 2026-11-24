"""Thin helpers around the AWS services the Lambdas use: S3, DynamoDB, SES and Bedrock.

DynamoDB table layout (one table, keys jobId + sk):
    sk = "META"                         the job: status, stage, owner, result, email status
    sk = "AUDIT#<timestamp>#<stage>"    one audit entry per stage output
    jobId = "USER#<id>", sk = "QUOTA#<day>"   per-user daily job counter
"""

import io
import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Any
from xml.sax.saxutils import escape

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common.errors import ThrottledError

BUCKET = os.environ.get("DATA_BUCKET", "")
TABLE = os.environ.get("JOBS_TABLE", "")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
SENDER = os.environ.get("SENDER_EMAIL", "")
RECORD_TTL = 30 * 24 * 3600  # DynamoDB records expire after 30 days
LINK_TTL = 900  # presigned PDF links are valid for 15 minutes

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
table = boto3.resource("dynamodb").Table(TABLE) if TABLE else None
ses = boto3.client("sesv2")
# No API key anywhere: boto3 signs Bedrock calls with the Lambda's IAM role.
bedrock = boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 3, "mode": "adaptive"}))


def response(status: int, body: dict) -> dict:
    """HTTP API response."""
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------- Bedrock


def converse(system: str, messages: list, tool_config: dict, max_tokens: int = 2048) -> tuple[dict, str]:
    """One model turn with tool use. Returns (assistant message, stop reason)."""
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": system}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"ThrottlingException", "ServiceUnavailableException"}:
            raise ThrottledError("The AI service is busy. Please retry shortly.") from exc  # Step Functions retries
        raise
    return response["output"]["message"], response.get("stopReason", "")


# ---------------------------------------------------------------- S3


def input_key(job_id: str, name: str) -> str:
    return f"uploads/{job_id}/{name}.txt"


def put_text(key: str, text: str) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=text.encode(), ContentType="text/plain; charset=utf-8")


def get_text(key: str) -> str:
    return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()


def put_pdf(key: str, data: bytes) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="application/pdf")


def get_pdf(key: str) -> bytes:
    return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()


def pdf_link(key: str) -> str:
    """Short-lived download link: the bucket itself stays private."""
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ResponseContentDisposition": 'attachment; filename="tailored-resume.pdf"',
        },
        ExpiresIn=LINK_TTL,
    )


# ---------------------------------------------------------------- DynamoDB: jobs


def _update(job_id: str, **fields: Any) -> None:
    """SET the given attributes on the job's META item."""
    fields["updatedAt"] = now()
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": json.loads(json.dumps(v), parse_float=Decimal) for k, v in fields.items()}
    table.update_item(
        Key={"jobId": job_id, "sk": "META"},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def create_job(job_id: str, user_id: str, email: str) -> None:
    table.put_item(
        Item={
            "jobId": job_id,
            "sk": "META",
            "status": "RUNNING",
            "stage": "queued",
            "userId": user_id,  # owner: only this user can read the job
            "email": email,  # deleted once the email has been sent
            "createdAt": now(),
            "expiresAt": int(time.time()) + RECORD_TTL,
        }
    )


def get_job(job_id: str) -> dict | None:
    return table.get_item(Key={"jobId": job_id, "sk": "META"}).get("Item")


def set_stage(job_id: str, stage: str) -> None:
    _update(job_id, stage=stage)  # the page polls this to show progress


def mark_done(job_id: str, result: dict, result_key: str) -> None:
    _update(job_id, status="DONE", stage="done", result=result, resultKey=result_key)


def mark_failed(job_id: str, code: str, message: str) -> None:
    _update(job_id, status="FAILED", errorCode=code, errorMessage=message)


def write_audit(job_id: str, stage: str, output: dict) -> None:
    """Audit log: store each stage's full output under the job id."""
    ts = now()
    table.put_item(
        Item={
            "jobId": job_id,
            "sk": f"AUDIT#{ts}#{stage}",
            "stage": stage,
            "timestamp": ts,
            "output": json.dumps(output, default=str),
            "expiresAt": int(time.time()) + RECORD_TTL,
        }
    )


def claim_daily_quota(user_id: str, limit: int = 5) -> bool:
    """Count one job for this user today. Returns False once the limit is reached (atomic)."""
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        table.update_item(
            Key={"jobId": f"USER#{user_id}", "sk": f"QUOTA#{day}"},
            UpdateExpression="ADD used :one SET expiresAt = :exp",
            ConditionExpression="attribute_not_exists(used) OR used < :limit",
            ExpressionAttributeValues={":one": 1, ":limit": limit, ":exp": int(time.time()) + 2 * 86400},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def plain(value: Any) -> Any:
    """DynamoDB returns numbers as Decimal; convert back for JSON."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- PDF + email


def build_pdf(result: dict) -> bytes:
    """Render score, summary, bullets and gap list as a one-page PDF (reportlab, from the Lambda layer)."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import ListFlowable, Paragraph, SimpleDocTemplate

    styles = getSampleStyleSheet()
    p = lambda text, style="BodyText": Paragraph(escape(text), styles[style])  # escape: model text is untrusted
    gaps = [f"{g['requirement']} ({g['category'].replace('_', ' ')}): {g['reason']}" for g in result["gaps"]]
    story = [p("Tailored Resume Draft", "Title"), p(f"Match score: {result['score']}/100")]
    if result.get("lowMatch"):
        story.append(p("This job does not match your resume, so no tailored draft was written. See the gap list below."))
    else:
        story += [
            p("Summary", "Heading2"),
            p(result["summary"]),
            p("Tailored bullets", "Heading2"),
            ListFlowable([p(b) for b in result["bullets"]], bulletType="bullet"),
        ]
    story += [
        p("Gap list (requirements your resume does not show yet)", "Heading2"),
        ListFlowable([p(g) for g in gaps] or [p("No gaps.")], bulletType="bullet"),
    ]
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=LETTER, title="Tailored Resume Draft").build(story)
    return buffer.getvalue()


def email_text(result: dict) -> str:
    lines = [f"Match score: {result['score']}/100", ""]
    if result.get("lowMatch"):
        lines += ["This job does not match your resume, so no tailored draft was written."]
    else:
        lines += ["SUMMARY", result["summary"], "", "TAILORED BULLETS"] + [f"- {b}" for b in result["bullets"]]
    lines += ["", "GAP LIST"] + [f"- {g['requirement']}: {g['reason']}" for g in result["gaps"]]
    return "\n".join(lines + ["", "The PDF is attached."])


def send_email(to: str, result: dict, pdf: bytes) -> tuple[str, str]:
    """Email the draft with the PDF attached. Returns (status, message); never raises."""
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Your tailored resume draft and gap list", SENDER, to
    msg.set_content(email_text(result))
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="tailored-resume.pdf")
    try:
        ses.send_email(FromEmailAddress=SENDER, Destination={"ToAddresses": [to]}, Content={"Raw": {"Data": msg.as_bytes()}})
    except ClientError as exc:
        print(f"SES send failed: {exc.response['Error']['Code']}")
        return "FAILED", "The email could not be sent (in SES sandbox mode the address must be verified). The PDF download still works."
    return "SENT", ""
