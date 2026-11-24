"""Stage 2 - match scorer: compare the resume with each requirement, list the gaps."""

from common import tools
from common.stage import stage


@stage("scorer")
def handler(event: dict) -> dict:
    inputs = event.get("inputs", {})
    docs = tools.read_inputs(inputs.get("resume_key"), inputs.get("job_key"))
    requirements = event["analysis"]["requirements"]  # stage 1's output, carried in the state
    return tools.score_match(docs["resume_text"], requirements)  # -> state $.match
