"""Job endpoints.

GET  /api/jobs/{jobId}        the page polls this every 3 seconds until the job is DONE or FAILED
POST /api/jobs/{jobId}/email  the user clicks "Email me this draft": send the PDF through SES
"""

from common import aws

response = aws.response


def handler(event, _context=None):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    job_id = (event.get("pathParameters") or {}).get("jobId", "")
    job = aws.get_job(job_id) if job_id else None

    if not job or job.get("userId") != claims.get("sub"):  # users can only see their own jobs
        return response(404, {"error": "Job not found."})

    if event.get("requestContext", {}).get("http", {}).get("method") == "POST":
        return send_email(job_id, job)

    body = {"jobId": job_id, "status": job["status"], "stage": job.get("stage")}
    if job["status"] == "DONE":
        body["result"] = aws.plain(job["result"])
        body["downloadUrl"] = aws.pdf_link(job["resultKey"])  # fresh 15-minute link on every poll
        body["emailStatus"] = job.get("emailStatus")  # None until the user asks for the email
    if job["status"] == "FAILED":
        body["error"] = job.get("errorMessage")  # e.g. "The job description is missing for this job..."
    return response(200, body)


def send_email(job_id: str, job: dict) -> dict:
    if job["status"] != "DONE":
        return response(409, {"error": "The draft is not ready yet."})
    if job.get("emailStatus") == "SENT":
        return response(200, {"emailStatus": "SENT"})  # only once per job

    result = aws.plain(job["result"])
    status, message = aws.send_email(job["email"], result, aws.get_pdf(job["resultKey"]))
    aws.table.update_item(  # record the outcome; delete the address once sent (privacy)
        Key={"jobId": job_id, "sk": "META"},
        UpdateExpression="SET emailStatus = :s" + (" REMOVE email" if status == "SENT" else ""),
        ExpressionAttributeValues={":s": status},
    )
    if status != "SENT":
        return response(502, {"error": message})
    return response(200, {"emailStatus": "SENT"})
