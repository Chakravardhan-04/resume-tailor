"""POST /api/submit - validate the two documents, store them, start the Step Functions pipeline.

Returns a job id straight away (HTTP 202): the three AI stages take longer than API Gateway's 29 s limit,
so the page polls GET /api/jobs/{id} instead of waiting.
"""

import json
import os
import uuid

import boto3

from common import aws
from common.errors import InputError
from common.guardrails import validate_document

response = aws.response

stepfunctions = boto3.client("stepfunctions")


def handler(event, _context=None):
    # Who is calling: API Gateway already validated the Cognito token, we only read its claims.
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    if not claims.get("sub") or claims.get("email_verified") != "true":
        return response(401, {"error": "Please sign in with a verified email."})
    user_id, email = claims["sub"], claims["email"]  # results go to the account's email, never one from the body

    # Input guardrail: both documents present and within the length caps.
    try:
        body = json.loads(event.get("body") or "{}")
        resume = validate_document("resume", body.get("resume"))
        job_text = validate_document("job description", body.get("jobDescription"))
    except InputError as exc:
        return response(400, {"error": exc.message})
    except (json.JSONDecodeError, AttributeError):
        return response(400, {"error": "Send a JSON body with resume and jobDescription."})

    if not aws.claim_daily_quota(user_id):  # cost guard: 15 jobs per user per day
        return response(429, {"error": "Daily limit reached. Please try again tomorrow."})

    job_id = str(uuid.uuid4())
    inputs = {"resume_key": aws.input_key(job_id, "resume"), "job_key": aws.input_key(job_id, "job")}
    aws.put_text(inputs["resume_key"], resume)
    aws.put_text(inputs["job_key"], job_text)
    aws.create_job(job_id, user_id, email)

    # The state machine input is the pipeline's memory; each stage adds its output to it.
    stepfunctions.start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        name=job_id,
        input=json.dumps({"jobId": job_id, "inputs": inputs}),
    )
    return response(202, {"jobId": job_id})
