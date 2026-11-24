"""Input and output guardrails (Day-4 reliability + honesty rule)."""

import re
from typing import Any

from common import config
from common.errors import InputError

REDACTED = "[REDACTED]"

# Patterns for credentials that must never leave the pipeline.
_SECRET_PATTERNS = [
    re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[A-Z0-9]{16}\b"),  # AWS access key ids
    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S{20,}"),
    re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----|$)"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),  # generic API secret keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT
]


def validate_document(name: str, text: Any) -> str:
    """Return the trimmed document or raise InputError with a clear message."""
    if not isinstance(text, str) or not text.strip():
        raise InputError(f"The {name} is missing. Please provide both a resume and a job description.")
    cleaned = text.replace("\x00", "").strip()
    if len(cleaned) < config.min_doc_chars():
        raise InputError(f"The {name} is too short (minimum {config.min_doc_chars()} characters).")
    if len(cleaned) > config.max_doc_chars():
        raise InputError(f"The {name} is too long (maximum {config.max_doc_chars()} characters).")
    return cleaned


_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+"
)


def validate_email(value: Any) -> str:
    """Return a normalized email address or raise InputError. Rejects header-injection characters."""
    if not isinstance(value, str) or not value.strip():
        raise InputError("Please enter an email address to receive the result.")
    email = value.strip()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise InputError("Please enter a valid email address.")
    return email


def redact_secrets(text: str) -> str:
    """Replace anything that looks like a credential."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_secrets_deep(value: Any) -> Any:
    """Apply `redact_secrets` to every string inside a JSON-like structure."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_secrets_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_secrets_deep(v) for k, v in value.items()}
    return value


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


_NUMBER = re.compile(r"\d[\d,.]*")


def numbers_supported(text: str, source: str) -> bool:
    """True if every number in `text` also appears in `source` (blocks invented metrics)."""
    source_numbers = {n.rstrip(",.") for n in _NUMBER.findall(source)}
    return all(n.rstrip(",.") in source_numbers for n in _NUMBER.findall(text))


def quote_in_source(quote: str, source: str) -> bool:
    """True if `quote` appears verbatim (ignoring whitespace/case) in `source`.

    Backbone of the honesty guardrail: any claim the model makes must point at
    text that really exists in the original resume.
    """
    q = _normalize(quote)
    return len(q) >= 3 and q in _normalize(source)
