"""Stage 3, rewriter: tailor the summary and bullets under the honesty guardrail, then deliver.

Honesty layers (the prompt is only the first; 2-5 are code and cannot be talked around):
  1. prompt rules: gaps are "do not mention", no new numbers, outcomes, scope or skill levels
  2. every bullet cites a `source_quote` that exists verbatim in the resume
  3. no number, claim word ("production", "led", "expert", ...) or gap term ("Kubernetes") that the resume lacks
  4. a separate verifier agent fact-checks the surviving draft against the resume
  5. fail closed: if no bullet survives the job fails; if only the summary keeps failing, it is replaced by
     verbatim resume sentences that matched the job (honest by construction)
"""

import json
import logging
from typing import Any

from common import config, jobs, mailer, pdf, prompts, storage, tools
from common.agent import AnswerTool, run_agent
from common.errors import GuardrailError
from common.guardrails import (
    gap_terms,
    mentions_any,
    numbers_supported,
    quote_in_source,
    redact_secrets_deep,
    unsupported_claims,
)
from common.stage import stage_handler

logger = logging.getLogger(__name__)

TARGET_BULLETS = 4
MAX_BULLETS = 8

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-4 sentence professional summary."},
        "bullets": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_BULLETS,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_quote": {"type": "string", "description": "Verbatim resume excerpt, max 200 chars."},
                },
                "required": ["text", "source_quote"],
            },
        },
    },
    "required": ["summary", "bullets"],
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_supported": {"type": "boolean"},
        "unsupported_bullets": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Zero-based indexes of bullets not supported by the resume.",
        },
        "notes": {"type": "string"},
    },
    "required": ["summary_supported", "unsupported_bullets"],
}


def validate_draft(data: dict[str, Any]) -> dict[str, Any]:
    summary = str(data.get("summary", "")).strip()
    bullets = data.get("bullets")
    if not summary:
        raise ValueError('"summary" is required')
    if not isinstance(bullets, list) or not bullets:
        raise ValueError('"bullets" must be a non-empty list')
    cleaned = []
    for b in bullets[:MAX_BULLETS]:
        text, quote = str(b.get("text", "")).strip(), str(b.get("source_quote", "")).strip()
        if text and quote:
            cleaned.append({"text": text, "source_quote": quote})
    if not cleaned:
        raise ValueError('every bullet needs "text" and "source_quote"')
    return {"summary": summary, "bullets": cleaned}


def validate_verdict(count: int):
    def validate(data: dict[str, Any]) -> dict[str, Any]:
        flagged = data.get("unsupported_bullets", [])
        if not isinstance(flagged, list) or not all(isinstance(i, int) and 0 <= i < count for i in flagged):
            raise ValueError(f'"unsupported_bullets" must be a list of integers between 0 and {count - 1}')
        if not isinstance(data.get("summary_supported"), bool):
            raise ValueError('"summary_supported" must be true or false')
        notes = str(data.get("notes") or "")[:500]
        return {"summary_supported": data["summary_supported"], "unsupported_bullets": flagged, "notes": notes}

    return validate


def problems(text: str, resume: str, forbidden: list[str]) -> list[str]:
    """Words or numbers in `text` the resume does not support (empty list = acceptable)."""
    found = unsupported_claims(text, resume) + mentions_any(text, forbidden)
    if not numbers_supported(text, resume):
        found.append("numbers that are not in the resume")
    return found


def filter_deterministic(
    draft: dict[str, Any], resume: str, forbidden: list[str]
) -> tuple[list[dict], list[str], list[str]]:
    """Layers 2 and 3. Returns (surviving bullets, summary issues, bullet issues)."""
    kept, bullet_issues = [], set()
    for bullet in draft["bullets"]:
        issues = problems(bullet["text"], resume, forbidden)
        bullet_issues.update(issues)
        if quote_in_source(bullet["source_quote"], resume) and not issues:
            kept.append(bullet)
    return kept, problems(draft["summary"], resume, forbidden), sorted(bullet_issues)


def fallback_summary(match: dict[str, Any], resume: str, forbidden: list[str]) -> str | None:
    """Verbatim resume sentences that matched the job: honest by construction. Used only as a last resort."""
    picked: list[str] = []
    for item in match["matched"]:
        quote = item["evidence"].strip().rstrip(".") + "."
        if quote not in picked and "..." not in quote and not problems(quote, resume, forbidden):
            picked.append(quote)
        if len(picked) == 2:
            break
    return " ".join(picked) or None


def feedback_for(summary_issues: list[str], bullet_issues: list[str], notes: str) -> str:
    parts = [
        "Some content was not supported by the resume and was removed. Use only facts, wording and numbers "
        "that appear in the resume, and cite an exact source_quote for every bullet."
    ]
    if summary_issues:
        parts.append(f"In the summary, remove: {', '.join(summary_issues)}.")
    if bullet_issues:
        parts.append(f"In the bullets, do not use: {', '.join(bullet_issues)}.")
    if notes:
        parts.append(f"Fact-checker notes: {notes}")
    return " ".join(parts)


def verify(resume: str, draft: dict[str, Any], bullets: list[dict]) -> dict[str, Any]:
    """Layer 4: an independent fact-check of the surviving draft."""
    numbered = "\n".join(f"{i}. {b['text']}" for i, b in enumerate(bullets))
    user = (
        f"<resume>\n{resume}\n</resume>\n\n<summary>\n{draft['summary']}\n</summary>\n\n"
        f"<bullets>\n{numbered}\n</bullets>"
    )
    answer = AnswerTool(
        name="submit_verdict",
        description="Submit which parts of the draft are not supported by the resume.",
        input_schema=VERDICT_SCHEMA,
        validate=validate_verdict(len(bullets)),
    )
    return run_agent("verifier", prompts.VERIFIER, user, answer, max_iterations=2)


def build_user_prompt(resume: str, match: dict[str, Any], feedback: str) -> str:
    emphasise = [m["requirement"] for m in match["matched"]]
    gaps = [g["requirement"] for g in match["gaps"]]
    prompt = (
        f"<emphasise_these_demonstrated_requirements>\n{json.dumps(emphasise)}\n"
        f"</emphasise_these_demonstrated_requirements>\n\n"
        f"<gaps_do_not_mention_or_imply>\n{json.dumps(gaps)}\n</gaps_do_not_mention_or_imply>\n\n"
        f"<resume>\n{resume}\n</resume>"
    )
    return f"{prompt}\n\nFix these problems from your previous attempt: {feedback}" if feedback else prompt


def tailor(resume: str, match: dict[str, Any]) -> dict[str, Any]:
    """Bounded generate -> filter -> verify loop. Fails closed if nothing honest survives."""
    forbidden = gap_terms([g["requirement"] for g in match["gaps"]], resume)
    draft_tool = AnswerTool(
        name="submit_draft",
        description="Submit the tailored summary and bullets, each bullet with its verbatim source_quote.",
        input_schema=DRAFT_SCHEMA,
        validate=validate_draft,
    )
    feedback = ""
    best_bullets: list[dict] = []
    best_summary: str | None = None
    for attempt in range(1, config.max_iterations() + 1):
        draft = run_agent(
            "rewriter",
            prompts.REWRITER,
            build_user_prompt(resume, match, feedback),
            draft_tool,
            max_iterations=2,
            max_tokens=3000,
        )
        bullets, summary_issues, bullet_issues = filter_deterministic(draft, resume, forbidden)
        dropped = len(draft["bullets"]) - len(bullets)
        notes = ""
        if bullets:
            verdict = verify(resume, draft, bullets)
            if not verdict["summary_supported"]:
                summary_issues = summary_issues or ["claims the fact-checker could not find in the resume"]
            flagged = set(verdict["unsupported_bullets"])
            dropped += len(flagged)
            bullets = [b for i, b in enumerate(bullets) if i not in flagged]
            notes = verdict["notes"]
        summary_ok = not summary_issues
        logger.info("rewrite attempt=%d kept=%d dropped=%d summary_ok=%s", attempt, len(bullets), dropped, summary_ok)

        if len(bullets) >= len(best_bullets):
            best_bullets = bullets
        if summary_ok and best_summary is None:
            best_summary = draft["summary"]
        if best_summary and len(best_bullets) >= TARGET_BULLETS:
            break
        if best_summary and not dropped:
            break
        feedback = feedback_for(summary_issues, bullet_issues, notes)

    if not best_bullets:
        raise GuardrailError(
            "A tailored draft could not be produced without adding content that is not in your resume. "
            "Your original resume may need more detail."
        )
    if best_summary is None:
        best_summary = fallback_summary(match, resume, forbidden)
        logger.info("rewrite summary=fallback_verbatim")
        if best_summary is None:
            raise GuardrailError("A summary could not be written using only facts from your resume.")
    return {"summary": best_summary, "bullets": [b["text"] for b in best_bullets]}


def deliver_email(job_id: str, result: dict[str, Any], pdf_bytes: bytes) -> str:
    """Send the result to the account's address. Never raises: the result is already stored."""
    try:
        recipient = (jobs.get_job(job_id) or {}).get("email")
        if not recipient:
            return "SKIPPED"
        status, message = mailer.send_result_email(recipient, result, pdf_bytes)
        jobs.set_email_status(job_id, status, message)
        return status
    except Exception:
        logger.exception("email delivery failed for job=%s", job_id)
        return "FAILED"


@stage_handler("rewriter")
def handler(event: dict[str, Any]) -> dict[str, Any]:
    job_id = event["jobId"]
    inputs = event.get("inputs") or {}
    resume = tools.read_inputs(resume_key=inputs.get("resume_key"), job_key=inputs.get("job_key"))["resume_text"]
    match = event["match"]

    draft = tailor(resume, match)
    result = {
        "score": match["score"],
        "summary": draft["summary"],
        "bullets": draft["bullets"],
        "gaps": [{k: g[k] for k in ("requirement", "category", "reason")} for g in match["gaps"]],
        "matched": [{"requirement": m["requirement"], "evidence": m["evidence"]} for m in match["matched"]],
    }
    result = redact_secrets_deep(result)  # output guardrail: no leaked secrets

    key = storage.result_key(job_id)
    pdf_bytes = pdf.build_pdf(result)
    storage.put_pdf(key, pdf_bytes)
    email_status = deliver_email(job_id, result, pdf_bytes)  # before DONE so the page sees the outcome
    jobs.mark_done(job_id, result, key)  # DONE only after the PDF is stored and email attempted
    return {"resultKey": key, "result": result, "emailStatus": email_status}
