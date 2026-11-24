"""GET /api/jobs/{jobId}: job status, result, and a fresh presigned PDF link when done."""

import logging
import re

from common import jobs, storage
from common.http import Unauthorized, caller, response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def handler(event, _context=None):
    try:
        user_id, _email = caller(event)
    except Unauthorized as exc:
        return response(401, {"error": str(exc)})

    job_id = (event.get("pathParameters") or {}).get("jobId", "")
    if not _UUID.match(job_id):
        return response(400, {"error": "Invalid job id."})

    try:
        job = jobs.get_job(job_id)
    except Exception:
        logger.exception("status lookup failed for job=%s", job_id)
        return response(500, {"error": "Could not read job status."})
    if job is None or job.get("userId") != user_id:  # same 404 for "not yours" and "not found"
        return response(404, {"error": "Job not found (it may have expired)."})

    body = {"jobId": job_id, "status": job["status"], "stage": job.get("stage")}
    if job["status"] == "DONE":
        body["result"] = jobs.to_plain(job.get("result"))
        body["downloadUrl"] = storage.presign_pdf(job["resultKey"])  # generated per poll; never stored
        body["email"] = {"status": job.get("emailStatus", "SKIPPED"), "message": job.get("emailMessage") or None}
    elif job["status"] == "FAILED":
        body["error"] = {"code": job.get("errorCode"), "message": job.get("errorMessage")}
    return response(200, body)
