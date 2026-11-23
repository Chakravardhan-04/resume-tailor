"""S3 access: read_inputs tool, result PDF, presigned download URLs."""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common import config
from common.errors import InputError

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        # SigV4 + regional endpoint so presigned URLs work immediately after deploy.
        _s3 = boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return _s3


def input_key(job_id: str, name: str) -> str:
    return f"uploads/{job_id}/{name}.txt"


def result_key(job_id: str) -> str:
    return f"results/{job_id}.pdf"


def put_text(key: str, text: str) -> None:
    _client().put_object(
        Bucket=config.bucket_name(),
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
        ServerSideEncryption="AES256",
    )


def get_text(key: str) -> str:
    obj = _client().get_object(Bucket=config.bucket_name(), Key=key)
    return obj["Body"].read().decode("utf-8")


def put_pdf(key: str, data: bytes) -> None:
    _client().put_object(
        Bucket=config.bucket_name(),
        Key=key,
        Body=data,
        ContentType="application/pdf",
        ServerSideEncryption="AES256",
    )


def presign_pdf(key: str, filename: str = "tailored-resume.pdf") -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": config.bucket_name(),
            "Key": key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=config.download_url_ttl_seconds(),
    )


def read_inputs(job_id: str) -> tuple[str, str]:
    """Tool `read_inputs`: load (resume, job description) for a job.

    A missing document escalates with a clear, user-facing message.
    """
    docs = {}
    for name, label in (("resume", "resume"), ("job", "job description")):
        try:
            docs[name] = get_text(input_key(job_id, name))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise InputError(
                    f"The {label} could not be found for this job. Please submit both a resume and a job description."
                ) from exc
            raise
    return docs["resume"], docs["job"]
