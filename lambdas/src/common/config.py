"""Runtime configuration, read lazily from environment variables."""

import os

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def model_id() -> str:
    return os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)


def bucket_name() -> str:
    return os.environ["DATA_BUCKET"]


def table_name() -> str:
    return os.environ["JOBS_TABLE"]


def state_machine_arn() -> str:
    return os.environ["STATE_MACHINE_ARN"]


def max_doc_chars() -> int:
    """Upper length cap for each input document."""
    return _int("MAX_DOC_CHARS", 15000)


def min_doc_chars() -> int:
    return _int("MIN_DOC_CHARS", 50)


def max_iterations() -> int:
    """Bound on the model loop inside a single stage."""
    return _int("MAX_AGENT_ITERATIONS", 3)


def download_url_ttl_seconds() -> int:
    return _int("DOWNLOAD_URL_TTL_SECONDS", 900)


def record_ttl_seconds() -> int:
    """How long job + audit records live in DynamoDB."""
    return _int("RECORD_TTL_SECONDS", 30 * 24 * 3600)


def sender_email() -> str:
    """Verified SES sender address (empty when email is not configured)."""
    return os.environ.get("SENDER_EMAIL", "")
