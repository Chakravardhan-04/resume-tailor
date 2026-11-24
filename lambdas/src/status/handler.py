"""GET /api/jobs/{jobId} - the page polls this every 3 seconds until the job is DONE or FAILED."""

from common import aws

response = aws.response


def handler(event, _context=None):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    job_id = (event.get("pathParameters") or {}).get("jobId", "")
    job = aws.get_job(job_id) if job_id else None

    if not job or job.get("userId") != claims.get("sub"):  # users can only see their own jobs
        return response(404, {"error": "Job not found."})

    body = {"jobId": job_id, "status": job["status"], "stage": job.get("stage")}
    if job["status"] == "DONE":
        body["result"] = aws.plain(job["result"])
        body["downloadUrl"] = aws.pdf_link(job["resultKey"])  # fresh 15-minute link on every poll
        body["email"] = {"status": job.get("emailStatus"), "message": job.get("emailMessage")}
    if job["status"] == "FAILED":
        body["error"] = job.get("errorMessage")  # e.g. "The job description is missing for this job..."
    return response(200, body)
