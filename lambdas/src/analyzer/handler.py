"""Stage 1, requirement-analyzer: read_inputs -> extract_requirements."""

from typing import Any

from common import tools
from common.stage import stage_handler


@stage_handler("analyzer")
def handler(event: dict[str, Any]) -> dict[str, Any]:
    inputs = event.get("inputs") or {}
    docs = tools.read_inputs(resume_key=inputs.get("resume_key"), job_key=inputs.get("job_key"))
    return tools.extract_requirements(job_text=docs["job_text"])
