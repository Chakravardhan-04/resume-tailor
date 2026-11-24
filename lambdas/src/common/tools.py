"""The three tools from the project spec.

    read_inputs(resume_key, job_key)              S3 read     -> {resume_text, job_text}
    extract_requirements(job_text)                LLM-driven  -> {requirements: [...]}
    score_match(resume_text, requirements)        LLM-driven  -> {score, matched, gaps}

Each tool checks its required inputs first. Missing input raises InputError, which fails the job
with a clear message (Step Functions does not retry it).
"""

import json

from botocore.exceptions import ClientError

from common import aws, prompts
from common.agent import AnswerTool, run_agent
from common.errors import InputError
from common.guardrails import quote_in_source, validate_document


def require(tool: str, **inputs) -> None:
    """Escalate clearly when a required input is missing or empty."""
    for name, value in inputs.items():
        if not value or (isinstance(value, str) and not value.strip()):
            raise InputError(f"{tool}: required input '{name}' is missing or empty.")


# ---------------------------------------------------------------- read_inputs


def read_inputs(resume_key: str, job_key: str) -> dict:
    """Load the resume and job description from S3 and apply the length caps."""
    require("read_inputs", resume_key=resume_key, job_key=job_key)
    return {
        "resume_text": validate_document("resume", load(resume_key, "resume")),
        "job_text": validate_document("job description", load(job_key, "job description")),
    }


def load(key: str, label: str) -> str:
    try:
        return aws.get_text(key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":  # forced-failure demo: upload only one file
            raise InputError(f"The {label} is missing for this job. Please submit both a resume and a job description.") from exc
        raise


# ---------------------------------------------------------------- extract_requirements

REQUIREMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "category": {"type": "string", "enum": ["must_have", "nice_to_have"]},
                },
                "required": ["text", "category"],
            },
        }
    },
    "required": ["requirements"],
}


def check_requirements(answer: dict) -> dict:
    items = answer.get("requirements") or []
    if not 1 <= len(items) <= 25:
        raise ValueError("return between 1 and 25 requirements")
    for item in items:
        if item.get("category") not in ("must_have", "nice_to_have") or not str(item.get("text", "")).strip():
            raise ValueError("every requirement needs text and a category of must_have or nice_to_have")
    # ids are assigned in code, so they are always unique: R1, R2, ...
    return {"requirements": [{"id": f"R{i}", "text": r["text"].strip(), "category": r["category"]} for i, r in enumerate(items, 1)]}


def extract_requirements(job_text: str) -> dict:
    require("extract_requirements", job_text=job_text)
    tool = AnswerTool("submit_requirements", "Submit the job's requirements.", REQUIREMENTS_SCHEMA, check_requirements)
    return run_agent("analyzer", prompts.ANALYZER, f"<job_description>\n{job_text}\n</job_description>", tool)


# ---------------------------------------------------------------- score_match

JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "matched": {
            "type": "array",
            "items": {"type": "object", "properties": {"id": {"type": "string"}, "evidence": {"type": "string"}}},
        },
        "gaps": {
            "type": "array",
            "items": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}},
        },
    },
    "required": ["matched", "gaps"],
}

WEIGHTS = {"must_have": 2, "nice_to_have": 1}  # must-haves count double in the score


def score_match(resume_text: str, requirements: list) -> dict:
    require("score_match", resume_text=resume_text, requirements=requirements)
    ids = {r["id"] for r in requirements}

    def check(answer: dict) -> dict:
        seen = [str(x.get("id")) for x in answer.get("matched", []) + answer.get("gaps", [])]
        if sorted(seen) != sorted(ids):
            raise ValueError(f"put every requirement id exactly once in matched or gaps: {sorted(ids)}")
        fake = [m["id"] for m in answer["matched"] if not quote_in_source(str(m.get("evidence", "")), resume_text)]
        if fake:  # evidence must be copied word for word from the resume
            raise ValueError(f"evidence for {fake} is not copied verbatim from the resume; quote it exactly or move it to gaps")
        return answer

    tool = AnswerTool("submit_judgement", "Submit evidence or a gap reason for every requirement.", JUDGEMENT_SCHEMA, check)
    listing = json.dumps([{"id": r["id"], "text": r["text"]} for r in requirements])
    judgement = run_agent("scorer", prompts.SCORER, f"<requirements>{listing}</requirements>\n<resume>\n{resume_text}\n</resume>", tool)

    # The score is computed in code, not by the model.
    by_id = {r["id"]: r for r in requirements}

    def entry(item: dict, **extra) -> dict:
        req = by_id[item["id"]]
        return {"id": req["id"], "requirement": req["text"], "category": req["category"], **extra}

    matched = [entry(m, evidence=m["evidence"]) for m in judgement["matched"]]
    gaps = [entry(g, reason=g.get("reason", "")) for g in judgement["gaps"]]
    total = sum(WEIGHTS[r["category"]] for r in requirements)
    earned = sum(WEIGHTS[m["category"]] for m in matched)
    return {"score": round(100 * earned / total), "matched": matched, "gaps": gaps}
