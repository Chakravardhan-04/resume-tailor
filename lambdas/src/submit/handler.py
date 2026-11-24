"""POST /api/submit: validate inputs, store them, create the job, start the state machine."""

import json
import logging
import uuid

import boto3

from common import config, jobs, storage
from common.errors import InputError
from common.guardrails import validate_document, validate_email
from common.http import parse_json_body, response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_sfn = None


def _stepfunctions():
    global _sfn
    if _sfn is None:
        _sfn = boto3.client("stepfunctions")
    return _sfn


def handler(event, _context=None):
    try:
        body = parse_json_body(event)
        resume = validate_document("resume", body.get("resume"))
        job_text = validate_document("job description", body.get("jobDescription"))
        email = validate_email(body.get("email"))
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except InputError as exc:
        return response(400, {"error": exc.user_message})

    job_id = str(uuid.uuid4())
    try:
        storage.put_text(storage.input_key(job_id, "resume"), resume)
        storage.put_text(storage.input_key(job_id, "job"), job_text)
        jobs.create_job(job_id, email)
        _stepfunctions().start_execution(
            stateMachineArn=config.state_machine_arn(), name=job_id, input=json.dumps({"jobId": job_id})
        )
    except Exception:
        logger.exception("submit failed for job=%s", job_id)
        return response(500, {"error": "Could not start the job. Please try again."})

    logger.info("job=%s started", job_id)
    return response(202, {"jobId": job_id})
