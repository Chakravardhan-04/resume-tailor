"""Stage 1: requirement-analyzer. Reads both inputs (read_inputs tool) and extracts JD requirements."""

from typing import Any

from common import llm, prompts, storage
from common.guardrails import validate_document
from common.stage import stage_handler

CATEGORIES = {"must_have", "nice_to_have"}
TYPES = {"skill", "experience", "education", "certification", "other"}
MAX_REQUIREMENTS = 25


def validate_requirements(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("requirements")
    if not isinstance(items, list) or not items:
        raise ValueError('"requirements" must be a non-empty list')
    if len(items) > MAX_REQUIREMENTS:
        raise ValueError(f"at most {MAX_REQUIREMENTS} requirements allowed")
    cleaned = []
    for i, item in enumerate(items, start=1):
        text = str(item.get("text", "")).strip()
        if not text:
            raise ValueError(f"requirement {i} has no text")
        if item.get("category") not in CATEGORIES:
            raise ValueError(f"requirement {i} category must be one of {sorted(CATEGORIES)}")
        rtype = item.get("type") if item.get("type") in TYPES else "other"
        # Ids are assigned here so they are always unique and sequential.
        cleaned.append({"id": f"R{i}", "text": text[:200], "category": item["category"], "type": rtype})
    return {"requirements": cleaned}


@stage_handler("analyzer")
def _run(event: dict[str, Any]) -> dict[str, Any]:
    resume, job_text = storage.read_inputs(event["jobId"])
    validate_document("resume", resume)
    job_text = validate_document("job description", job_text)
    user = f"<job_description>\n{job_text}\n</job_description>"
    return llm.converse_json(prompts.ANALYZER, user, validate_requirements)


handler = _run
