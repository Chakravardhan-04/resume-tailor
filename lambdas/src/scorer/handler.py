"""Stage 2, match-scorer: read_inputs -> score_match (uses $.analysis from the state)."""

from typing import Any

from common import tools
from common.stage import stage_handler


@stage_handler("scorer")
def handler(event: dict[str, Any]) -> dict[str, Any]:
    inputs = event.get("inputs") or {}
    docs = tools.read_inputs(resume_key=inputs.get("resume_key"), job_key=inputs.get("job_key"))
    return tools.score_match(resume_text=docs["resume_text"], requirements=event["analysis"]["requirements"])
