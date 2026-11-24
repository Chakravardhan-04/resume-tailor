"""Stage 1 - requirement analyzer: load the documents, extract the job's requirements."""

from common import tools
from common.stage import stage


@stage("analyzer")
def handler(event: dict) -> dict:
    inputs = event.get("inputs", {})  # S3 keys put in the state by the submit Lambda
    docs = tools.read_inputs(inputs.get("resume_key"), inputs.get("job_key"))
    return tools.extract_requirements(docs["job_text"])  # -> state $.analysis
