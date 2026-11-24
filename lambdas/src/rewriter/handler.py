"""Stage 3: rewriter. Produces a tailored summary + bullets under the honesty guardrail, then the PDF.

Honesty is enforced in three independent layers (the prompt is only the first):
  1. every bullet must cite a verbatim `source_quote` that exists in the resume
  2. no number may appear that is absent from the resume
  3. a separate verifier call fact-checks the draft against the original resume
Unsupported bullets are dropped; unmet requirements stay in the gap list.
"""

import json
import logging
from typing import Any

from common import config, jobs, llm, mailer, pdf, prompts, storage
from common.errors import GuardrailError
from common.guardrails import numbers_supported, quote_in_source, redact_secrets_deep
from common.stage import stage_handler

logger = logging.getLogger(__name__)

TARGET_BULLETS = 4
MAX_BULLETS = 8


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
        return {"summary_supported": data["summary_supported"], "unsupported_bullets": flagged}

    return validate


def filter_deterministic(draft: dict[str, Any], resume: str) -> tuple[list[dict], bool]:
    """Layers 1 and 2. Returns (surviving bullets, summary_ok)."""
    kept = [
        b
        for b in draft["bullets"]
        if quote_in_source(b["source_quote"], resume) and numbers_supported(b["text"], resume)
    ]
    return kept, numbers_supported(draft["summary"], resume)


def verify(resume: str, draft: dict[str, Any], bullets: list[dict]) -> dict[str, Any]:
    """Layer 3. LLM fact-check of the surviving draft."""
    numbered = "\n".join(f"{i}. {b['text']}" for i, b in enumerate(bullets))
    user = (
        f"<resume>\n{resume}\n</resume>\n\n<summary>\n{draft['summary']}\n</summary>\n\n"
        f"<bullets>\n{numbered}\n</bullets>"
    )
    return llm.converse_json(prompts.VERIFIER, user, validate_verdict(len(bullets)), max_iterations=2)


def build_user_prompt(resume: str, match: dict[str, Any], feedback: str) -> str:
    emphasise = [m["requirement"] for m in match["matched"]]
    gaps = [g["requirement"] for g in match["gaps"]]
    prompt = (
        f"<emphasise_these_demonstrated_requirements>\n{json.dumps(emphasise)}\n</emphasise_these_demonstrated_requirements>\n\n"
        f"<gaps_do_not_mention_or_imply>\n{json.dumps(gaps)}\n</gaps_do_not_mention_or_imply>\n\n"
        f"<resume>\n{resume}\n</resume>"
    )
    return f"{prompt}\n\nFix these problems from your previous attempt: {feedback}" if feedback else prompt


def tailor(resume: str, match: dict[str, Any]) -> dict[str, Any]:
    """Bounded generate -> filter -> verify loop. Fails closed if nothing honest survives."""
    feedback = ""
    best: tuple[str, list[dict]] | None = None
    for attempt in range(1, config.max_iterations() + 1):
        draft = llm.converse_json(
            prompts.REWRITER,
            build_user_prompt(resume, match, feedback),
            validate_draft,
            max_tokens=3000,
            max_iterations=2,
        )
        bullets, summary_ok = filter_deterministic(draft, resume)
        dropped = len(draft["bullets"]) - len(bullets)
        if bullets:
            verdict = verify(resume, draft, bullets)
            summary_ok = summary_ok and verdict["summary_supported"]
            flagged = set(verdict["unsupported_bullets"])
            dropped += len(flagged)
            bullets = [b for i, b in enumerate(bullets) if i not in flagged]
        logger.info("rewrite attempt=%d kept=%d dropped=%d summary_ok=%s", attempt, len(bullets), dropped, summary_ok)

        if summary_ok and bullets:
            if best is None or len(bullets) >= len(best[1]):
                best = (draft["summary"], bullets)
            if len(bullets) >= TARGET_BULLETS or not dropped:
                break
        feedback = (
            "Some content was not supported by the resume and was removed. Use only facts, wording and numbers "
            "that appear in the resume, and cite an exact source_quote for every bullet."
        )

    if best is None:
        raise GuardrailError(
            "A tailored draft could not be produced without adding content that is not in your resume. "
            "Your original resume may need more detail."
        )
    return {"summary": best[0], "bullets": [b["text"] for b in best[1]]}


def deliver_email(job_id: str, result: dict[str, Any], pdf_bytes: bytes) -> str:
    """Send the result by email if the user gave an address. Never raises: the job result is already safe."""
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
def _run(event: dict[str, Any]) -> dict[str, Any]:
    job_id = event["jobId"]
    match = event["match"]
    resume, _ = storage.read_inputs(job_id)

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


handler = _run
