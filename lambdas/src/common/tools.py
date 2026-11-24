"""The pipeline's tools, as listed in the project spec.

| Tool                 | Kind        | Input                                     |
|----------------------|-------------|-------------------------------------------|
| read_inputs          | S3 read     | resume_key: string, job_key: string       |
| extract_requirements | LLM-driven  | job_text: string                          |
| score_match          | LLM-driven  | resume_text: string, requirements: array  |

Every tool validates its arguments against its schema first. Missing or empty input raises
InputError, whose message is shown to the user (the job is marked FAILED; nothing is retried).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError

from common import prompts, storage
from common.agent import AnswerTool, run_agent
from common.errors import InputError
from common.guardrails import quote_in_source, validate_document


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


def _check_args(spec: ToolSpec, args: dict[str, Any]) -> None:
    """Minimal JSON-schema check: required fields present, strings non-empty, arrays non-empty."""
    props = spec.input_schema["properties"]
    for field in spec.input_schema["required"]:
        value = args.get(field)
        kind = props[field]["type"]
        ok = (kind == "string" and isinstance(value, str) and value.strip()) or (
            kind == "array" and isinstance(value, list) and value
        )
        if not ok:
            raise InputError(f"{spec.name}: required input '{field}' is missing or empty.")


def tool(spec: ToolSpec) -> Callable:
    """Attach `spec` to a function and validate keyword arguments before it runs."""

    def decorate(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        def wrapper(**kwargs: Any) -> dict[str, Any]:
            _check_args(spec, kwargs)
            return fn(**kwargs)

        wrapper.spec = spec  # type: ignore[attr-defined]
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorate


# --------------------------------------------------------------------------- read_inputs

READ_INPUTS = ToolSpec(
    name="read_inputs",
    description=(
        "Load the candidate's resume and the target job description from S3. Pasted text and uploaded "
        "files are both stored as uploads/<jobId>/resume.txt and uploads/<jobId>/job.txt by the submit API. "
        "Returns {resume_text, job_text}. Fails with a clear message if either document is missing."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "resume_key": {"type": "string", "description": "S3 key of the resume, e.g. uploads/<jobId>/resume.txt"},
            "job_key": {"type": "string", "description": "S3 key of the job description, e.g. uploads/<jobId>/job.txt"},
        },
        "required": ["resume_key", "job_key"],
    },
)


def _load(key: str, label: str) -> str:
    if not key.startswith("uploads/"):
        raise InputError(f"The {label} location is invalid.")
    try:
        return storage.get_text(key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            raise InputError(
                f"The {label} is missing for this job. Please submit both a resume and a job description."
            ) from exc
        raise


@tool(READ_INPUTS)
def read_inputs(*, resume_key: str, job_key: str) -> dict[str, str]:
    """Load and length-check both documents."""
    return {
        "resume_text": validate_document("resume", _load(resume_key, "resume")),
        "job_text": validate_document("job description", _load(job_key, "job description")),
    }


# --------------------------------------------------------------------------- extract_requirements

EXTRACT_REQUIREMENTS = ToolSpec(
    name="extract_requirements",
    description=(
        "LLM-driven. Extract the requirements a job description states, each classified as must_have or "
        "nice_to_have and typed (skill, experience, education, certification, other). Returns "
        "{requirements: [{id, text, category, type}]} with ids R1..Rn."
    ),
    input_schema={
        "type": "object",
        "properties": {"job_text": {"type": "string", "description": "Full job description text."}},
        "required": ["job_text"],
    },
)

CATEGORIES = ("must_have", "nice_to_have")
TYPES = ("skill", "experience", "education", "certification", "other")
MAX_REQUIREMENTS = 25

SUBMIT_REQUIREMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_REQUIREMENTS,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The requirement, under 15 words."},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "type": {"type": "string", "enum": list(TYPES)},
                },
                "required": ["text", "category", "type"],
            },
        }
    },
    "required": ["requirements"],
}


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
            raise ValueError(f"requirement {i} category must be one of {list(CATEGORIES)}")
        rtype = item.get("type") if item.get("type") in TYPES else "other"
        # Ids are assigned in code so they are always unique and sequential.
        cleaned.append({"id": f"R{i}", "text": text[:200], "category": item["category"], "type": rtype})
    return {"requirements": cleaned}


@tool(EXTRACT_REQUIREMENTS)
def extract_requirements(*, job_text: str) -> dict[str, Any]:
    answer = AnswerTool(
        name="submit_requirements",
        description="Submit the requirements extracted from the job description.",
        input_schema=SUBMIT_REQUIREMENTS_SCHEMA,
        validate=validate_requirements,
    )
    return run_agent("analyzer", prompts.ANALYZER, f"<job_description>\n{job_text}\n</job_description>", answer)


# --------------------------------------------------------------------------- score_match

SCORE_MATCH = ToolSpec(
    name="score_match",
    description=(
        "LLM-driven. Judge a resume against each requirement using only evidence in the resume, then score it "
        "in code (must_have counts 2, nice_to_have 1; a match only counts if its quote really is in the resume). "
        "Returns {score: 0-100, matched: [{id, requirement, category, evidence}], "
        "gaps: [{id, requirement, category, reason}]}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "resume_text": {"type": "string", "description": "Full resume text."},
            "requirements": {
                "type": "array",
                "description": "Output of extract_requirements: [{id, text, category, type}].",
                "items": {"type": "object"},
            },
        },
        "required": ["resume_text", "requirements"],
    },
)

WEIGHTS = {"must_have": 2, "nice_to_have": 1}
NO_EVIDENCE = "No supporting evidence was found in the resume."

SUBMIT_JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "matched": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "evidence": {"type": "string", "description": "Verbatim quote from the resume, max 200 chars."},
                },
                "required": ["id", "evidence"],
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "reason": {"type": "string", "description": "One sentence: what is missing."},
                },
                "required": ["id", "reason"],
            },
        },
    },
    "required": ["matched", "gaps"],
}


def make_judgement_validator(requirement_ids: set[str], resume_text: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def validate(data: dict[str, Any]) -> dict[str, Any]:
        matched, gaps = data.get("matched", []), data.get("gaps", [])
        if not isinstance(matched, list) or not isinstance(gaps, list):
            raise ValueError('"matched" and "gaps" must be lists')
        seen = [str(x.get("id")) for x in matched + gaps]
        unknown = set(seen) - requirement_ids
        if unknown:
            raise ValueError(f"unknown requirement ids: {sorted(unknown)}")
        missing = requirement_ids - set(seen)
        if missing:
            raise ValueError(f"requirement ids missing from matched/gaps: {sorted(missing)}")
        if len(seen) != len(set(seen)):
            raise ValueError("each requirement id must appear exactly once")
        not_verbatim = [
            str(m.get("id")) for m in matched if not quote_in_source(str(m.get("evidence", "")), resume_text)
        ]
        if not_verbatim:
            raise ValueError(
                f"evidence for {not_verbatim} is not copied verbatim from the resume. Copy one exact sentence or "
                "phrase from the resume (join separate excerpts with '...'), or move the requirement to gaps."
            )
        return {"matched": matched, "gaps": gaps}

    return validate


def compute_score(requirements: list[dict], judgement: dict[str, Any], resume_text: str) -> dict[str, Any]:
    """Deterministic scoring. A 'match' without a real resume quote is downgraded to a gap (safety net;
    the validator already sends non-verbatim evidence back to the model)."""
    by_id = {r["id"]: r for r in requirements}
    matched, gaps = [], []
    for item in judgement["gaps"]:
        gaps.append(_gap(by_id[str(item["id"])], str(item.get("reason") or NO_EVIDENCE)))
    for item in judgement["matched"]:
        req = by_id[str(item["id"])]
        evidence = str(item.get("evidence", "")).strip()
        if quote_in_source(evidence, resume_text):
            matched.append(
                {"id": req["id"], "requirement": req["text"], "category": req["category"], "evidence": evidence}
            )
        else:
            gaps.append(_gap(req, NO_EVIDENCE))

    total = sum(WEIGHTS[r["category"]] for r in requirements)
    earned = sum(WEIGHTS[m["category"]] for m in matched)
    return {"score": round(100 * earned / total) if total else 0, "matched": matched, "gaps": gaps}


def _gap(req: dict, reason: str) -> dict[str, str]:
    return {"id": req["id"], "requirement": req["text"], "category": req["category"], "reason": reason}


@tool(SCORE_MATCH)
def score_match(*, resume_text: str, requirements: list[dict]) -> dict[str, Any]:
    answer = AnswerTool(
        name="submit_judgement",
        description="Submit, for every requirement id, either verbatim evidence or the reason it is a gap.",
        input_schema=SUBMIT_JUDGEMENT_SCHEMA,
        validate=make_judgement_validator({r["id"] for r in requirements}, resume_text),
    )
    listing = json.dumps([{"id": r["id"], "text": r["text"]} for r in requirements])
    user = f"<requirements>\n{listing}\n</requirements>\n\n<resume>\n{resume_text}\n</resume>"
    judgement = run_agent("scorer", prompts.SCORER, user, answer, max_tokens=3000)
    return compute_score(requirements, judgement, resume_text)


TOOLS = (read_inputs, extract_requirements, score_match)
