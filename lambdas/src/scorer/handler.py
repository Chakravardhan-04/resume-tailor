"""Stage 2: match-scorer. Judges the resume against each requirement and lists gaps."""

import json
from typing import Any

from common import llm, prompts, storage
from common.guardrails import quote_in_source
from common.stage import stage_handler

WEIGHTS = {"must_have": 2, "nice_to_have": 1}
NO_EVIDENCE = "No supporting evidence was found in the resume."


def make_validator(requirement_ids: set[str]):
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
        return {"matched": matched, "gaps": gaps}

    return validate


def score_match(requirements: list[dict], judgement: dict[str, Any], resume: str) -> dict[str, Any]:
    """Deterministic scoring. Any 'match' without a real resume quote is downgraded to a gap."""
    by_id = {r["id"]: r for r in requirements}
    matched, gaps = [], []
    for item in judgement["gaps"]:
        req = by_id[str(item["id"])]
        gaps.append(_gap(req, str(item.get("reason") or NO_EVIDENCE)))
    for item in judgement["matched"]:
        req = by_id[str(item["id"])]
        evidence = str(item.get("evidence", "")).strip()
        if quote_in_source(evidence, resume):
            matched.append(
                {"id": req["id"], "requirement": req["text"], "category": req["category"], "evidence": evidence}
            )
        else:
            gaps.append(_gap(req, NO_EVIDENCE))

    total = sum(WEIGHTS[r["category"]] for r in requirements)
    earned = sum(WEIGHTS[m["category"]] for m in matched)
    score = round(100 * earned / total) if total else 0
    return {"score": score, "matched": matched, "gaps": gaps}


def _gap(req: dict, reason: str) -> dict[str, str]:
    return {"id": req["id"], "requirement": req["text"], "category": req["category"], "reason": reason}


@stage_handler("scorer")
def _run(event: dict[str, Any]) -> dict[str, Any]:
    requirements = event["analysis"]["requirements"]
    resume, _ = storage.read_inputs(event["jobId"])
    listing = json.dumps([{"id": r["id"], "text": r["text"]} for r in requirements])
    user = f"<requirements>\n{listing}\n</requirements>\n\n<resume>\n{resume}\n</resume>"
    judgement = llm.converse_json(
        prompts.SCORER, user, make_validator({r["id"] for r in requirements}), max_tokens=3000
    )
    return score_match(requirements, judgement, resume)


handler = _run
