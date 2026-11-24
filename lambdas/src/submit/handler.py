"""POST /api/submit: validate inputs, store them, create the job, start the state machine."""

import json
import logging
import uuid

import boto3

from common import config, jobs, storage
from common.errors import InputError
from common.guardrails import validate_document, validate_email
from common.http import Unauthorized, caller, parse_json_body, response

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
        user_id, email = caller(event)
    except Unauthorized as exc:
        return response(401, {"error": str(exc)})

    try:
        body = parse_json_body(event)
        resume = validate_document("resume", body.get("resume"))
        job_text = validate_document("job description", body.get("jobDescription"))
        validate_email(email)  # defence in depth: never trust the claim blindly
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except InputError as exc:
        return response(400, {"error": exc.user_message})

    try:
        if not jobs.claim_daily_quota(user_id, config.max_jobs_per_user_per_day()):
            return response(429, {"error": "Daily limit reached. Please try again tomorrow."})
    except Exception:
        logger.exception("quota check failed")
        return response(500, {"error": "Could not start the job. Please try again."})

    job_id = str(uuid.uuid4())
    try:
        inputs = {"resume_key": storage.input_key(job_id, "resume"), "job_key": storage.input_key(job_id, "job")}
        storage.put_text(inputs["resume_key"], resume)
        storage.put_text(inputs["job_key"], job_text)
        jobs.create_job(job_id, email, user_id)
        # The state carries the S3 keys; each stage loads the documents with the read_inputs tool.
        _stepfunctions().start_execution(
            stateMachineArn=config.state_machine_arn(),
            name=job_id,
            input=json.dumps({"jobId": job_id, "inputs": inputs}),
        )
    except Exception:
        logger.exception("submit failed for job=%s", job_id)
        return response(500, {"error": "Could not start the job. Please try again."})

    logger.info("job=%s started", job_id)  # never log the email address
    return response(202, {"jobId": job_id})
