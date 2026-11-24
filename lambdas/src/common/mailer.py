"""Email the tailored draft + gap list (PDF attached) through SES."""

import logging
from email.message import EmailMessage
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common import config

logger = logging.getLogger(__name__)

SUBJECT = "Your tailored resume draft and gap list"
_client = None


def _ses():
    global _client
    if _client is None:
        _client = boto3.client("sesv2")
    return _client


def render_text(result: dict[str, Any]) -> str:
    lines = [f"Match score: {result['score']}/100", "", "SUMMARY", result["summary"], "", "TAILORED BULLETS"]
    lines += [f"- {b}" for b in result["bullets"]]
    lines += ["", "GAP LIST (requirements your resume does not yet demonstrate)"]
    if result["gaps"]:
        for g in result["gaps"]:
            label = "must have" if g["category"] == "must_have" else "nice to have"
            lines.append(f"- {g['requirement']} ({label}): {g['reason']}")
    else:
        lines.append("- None. Every stated requirement is supported by your resume.")
    lines += ["", "The PDF version is attached. This is an AI-generated draft: review it before sending to employers."]
    return "\n".join(lines)


def build_message(sender: str, recipient: str, result: dict[str, Any], pdf: bytes) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(render_text(result))
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="tailored-resume.pdf")
    return msg


def send_result_email(recipient: str, result: dict[str, Any], pdf: bytes) -> tuple[str, str | None]:
    """Returns (status, message). Never raises for SES-side problems: email must not fail the job."""
    sender = config.sender_email()
    if not sender:
        return "FAILED", "Email is not configured for this deployment."
    message = build_message(sender, recipient, result, pdf)
    try:
        _ses().send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [recipient]},
            Content={"Raw": {"Data": message.as_bytes()}},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("SES send failed: %s", code)
        if code in {"MessageRejected", "MailFromDomainNotVerifiedException"}:
            return "FAILED", (
                "The email could not be sent. While the SES account is in sandbox mode, "
                "the recipient address must be verified. You can still download the PDF."
            )
        return "FAILED", "The email could not be sent. You can still download the PDF."
    return "SENT", None
