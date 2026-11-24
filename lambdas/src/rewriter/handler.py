"""Stage 3 - rewriter: write a tailored summary + bullets WITHOUT inventing anything, then save the PDF.

Honesty guardrail (the prompt asks nicely; the code below enforces it):
    1. each bullet must quote the resume line it is based on (source_quote), word for word
    2. no claim words, gap skills or numbers the resume does not contain
    3. a second agent (the verifier) fact-checks what is left
    4. if nothing honest survives, fail instead of returning invented content
"""

import json

from common import aws, prompts, tools
from common.agent import AnswerTool, run_agent
from common.errors import GuardrailError
from common.guardrails import gap_terms, honesty_problems, quote_in_source, redact
from common.stage import stage

MAX_ATTEMPTS = 3  # bounded: write -> check -> verify at most 3 times
LOW_MATCH_SCORE = 20  # below this (or with no must-have matched) the job does not fit the resume


def is_low_match(match: dict) -> bool:
    """True when the resume shows almost nothing the job asks for, so tailoring would not help."""
    must_matched = any(m["category"] == "must_have" for m in match["matched"])
    return match["score"] < LOW_MATCH_SCORE or not must_matched


DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "source_quote": {"type": "string"}},
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
        "unsupported_bullets": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["summary_supported", "unsupported_bullets"],
}


def check_draft(answer: dict) -> dict:
    bullets = [b for b in answer.get("bullets", []) if b.get("text") and b.get("source_quote")]
    if not answer.get("summary") or not bullets:
        raise ValueError("give a summary and at least one bullet, each bullet with text and source_quote")
    return {"summary": answer["summary"], "bullets": bullets[:8]}


def verify(resume: str, summary: str, bullets: list) -> dict:
    """Second agent: an independent fact-check of the draft against the resume."""
    numbered = "\n".join(f"{i}. {b['text']}" for i, b in enumerate(bullets))
    tool = AnswerTool("submit_verdict", "Report unsupported parts of the draft.", VERDICT_SCHEMA, lambda a: a)
    user = f"<resume>\n{resume}\n</resume>\n<summary>{summary}</summary>\n<bullets>\n{numbered}\n</bullets>"
    return run_agent("verifier", prompts.VERIFIER, user, tool, max_turns=2)


def tailor(resume: str, match: dict) -> dict:
    gap_words = gap_terms([g["requirement"] for g in match["gaps"]], resume)  # e.g. ["Kubernetes", "Terraform"]
    tool = AnswerTool("submit_draft", "Submit the tailored summary and bullets.", DRAFT_SCHEMA, check_draft)
    feedback = ""
    best_bullets, best_summary = [], None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        user = (
            f"<show_these>{json.dumps([m['requirement'] for m in match['matched']])}</show_these>\n"
            f"<gaps_never_mention>{json.dumps([g['requirement'] for g in match['gaps']])}</gaps_never_mention>\n"
            f"<resume>\n{resume}\n</resume>\n{feedback}"
        )
        draft = run_agent("rewriter", prompts.REWRITER, user, tool, max_turns=2)

        # Guardrail layers 1 + 2: keep a bullet only if its quote is real and its wording is supported.
        bullets = [
            b for b in draft["bullets"] if quote_in_source(b["source_quote"], resume) and not honesty_problems(b["text"], resume, gap_words)
        ]
        summary_problems = honesty_problems(draft["summary"], resume, gap_words)

        # Guardrail layer 3: the verifier agent removes anything else it cannot find in the resume.
        if bullets:
            verdict = verify(resume, draft["summary"], bullets)
            bullets = [b for i, b in enumerate(bullets) if i not in verdict["unsupported_bullets"]]
            if not verdict["summary_supported"]:
                summary_problems = summary_problems or ["claims the fact-checker could not find"]

        dropped = len(draft["bullets"]) - len(bullets)
        print(f"rewrite attempt={attempt} kept={len(bullets)} dropped={dropped} summary_ok={not summary_problems}")
        if len(bullets) >= len(best_bullets):
            best_bullets = bullets
        if not summary_problems and best_summary is None:
            best_summary = draft["summary"]
        if best_summary and (dropped == 0 or len(best_bullets) >= 4):
            break  # good enough: stop the loop

        # Tell the model exactly what was rejected, then try again.
        feedback = "Your previous draft had unsupported content that was removed. Use only facts from the resume."
        if summary_problems:
            feedback += f" In the summary, remove: {', '.join(summary_problems)}."

    # Guardrail layer 4: fail closed.
    if not best_bullets:
        raise GuardrailError("A draft could not be written using only facts from your resume. Add more detail to it.")
    if best_summary is None:  # last resort: resume sentences that matched the job, honest by construction
        best_summary = " ".join(m["evidence"] for m in match["matched"][:2] if "..." not in m["evidence"])
    return {"summary": best_summary, "bullets": [b["text"] for b in best_bullets]}


@stage("rewriter")
def handler(event: dict) -> dict:
    job_id = event["jobId"]
    inputs = event.get("inputs", {})
    resume = tools.read_inputs(inputs.get("resume_key"), inputs.get("job_key"))["resume_text"]
    match = event["match"]  # stage 2's output, carried in the state

    # Low match: skip the rewrite (no AI calls) and return only the score and the gap list.
    low_match = is_low_match(match)
    draft = {"summary": "", "bullets": []} if low_match else tailor(resume, match)
    print(f"rewrite low_match={low_match} score={match['score']}")
    result = redact(  # output guardrail: no leaked secrets in the page, PDF, email or audit log
        {
            "score": match["score"],
            "lowMatch": low_match,
            "summary": draft["summary"],
            "bullets": draft["bullets"],
            "gaps": [{"requirement": g["requirement"], "category": g["category"], "reason": g["reason"]} for g in match["gaps"]],
            "matched": [{"requirement": m["requirement"], "evidence": m["evidence"]} for m in match["matched"]],
        }
    )

    # Deliver: store the PDF, then mark the job DONE. The user emails it from the page when happy with it.
    pdf_key = f"results/{job_id}.pdf"
    aws.put_pdf(pdf_key, aws.build_pdf(result))
    aws.mark_done(job_id, result, pdf_key)
    return {"resultKey": pdf_key, "result": result}  # -> state $.rewrite
