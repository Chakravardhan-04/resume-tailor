import json

import pytest

from common import jobs, llm, mailer, pdf, storage
from common.errors import GuardrailError
from common.guardrails import numbers_supported
from rewriter import handler as rewriter

MATCH = {
    "score": 80,
    "matched": [{"id": "R1", "requirement": "Python", "category": "must_have", "evidence": "Python and Flask"}],
    "gaps": [{"id": "R3", "requirement": "Kubernetes", "category": "nice_to_have", "reason": "Not mentioned"}],
}
REQS = [{"id": "R1", "text": "Python", "category": "must_have", "type": "skill"}]


def draft(bullets, summary="Backend engineer with Python experience."):
    return {"summary": summary, "bullets": bullets}


HONEST = {
    "text": "Built Python REST APIs serving 2M requests per day.",
    "source_quote": "REST APIs in Python and Flask",
}
FAKE_QUOTE = {"text": "Ran Kubernetes clusters in production.", "source_quote": "Ran Kubernetes clusters"}
FAKE_NUMBER = {"text": "Built APIs serving 50M requests per day.", "source_quote": "REST APIs in Python and Flask"}


def test_numbers_supported():
    assert numbers_supported("serving 2M requests, team of 3", "2M requests per day; team of 3")
    assert not numbers_supported("grew revenue 40%", "no figures here")
    assert numbers_supported("no numbers at all", "anything")


def test_filter_drops_fabricated_quotes_and_numbers(resume):
    kept, summary_ok, claims = rewriter.filter_deterministic(draft([HONEST, FAKE_QUOTE, FAKE_NUMBER]), resume)
    assert kept == [HONEST]
    assert summary_ok
    assert claims == ["production"]  # from the dropped Kubernetes bullet


def test_filter_flags_summary_with_invented_number(resume):
    _, summary_ok, _ = rewriter.filter_deterministic(draft([HONEST], summary="10 years of Python"), resume)
    assert not summary_ok


def _patch_llm(monkeypatch, drafts, verdicts):
    drafts, verdicts = iter(drafts), iter(verdicts)

    def fake(system, user, validate, **_):
        return validate(next(drafts) if "fact-checker" not in system else next(verdicts))

    monkeypatch.setattr(llm, "converse_json", fake)


def test_filter_drops_upgraded_scope_and_invented_outcomes(resume):
    inflated = {"text": "Managed production REST APIs in Python.", "source_quote": "REST APIs in Python and Flask"}
    outcome = {
        "text": "Built REST APIs in Python, improving code quality.",
        "source_quote": "REST APIs in Python and Flask",
    }
    led = {"text": "Led a team of 3 engineers on a migration project.", "source_quote": "Led a team of 3 engineers"}
    kept, summary_ok, claims = rewriter.filter_deterministic(
        draft([inflated, outcome, led], summary="Expert backend engineer."), resume
    )
    assert kept == [led]  # "Led" appears in the resume, so it is allowed
    assert not summary_ok
    assert claims == ["expert", "improving", "managed", "production"]


def test_tailor_feeds_unsupported_words_back_to_the_model(monkeypatch, resume):
    inflated = {"text": "Managed production REST APIs in Python.", "source_quote": "REST APIs in Python and Flask"}
    prompts_seen = []

    def fake(system, user, validate, **_):
        if "fact-checker" in system:
            return validate({"summary_supported": True, "unsupported_bullets": []})
        prompts_seen.append(user)
        return validate(draft([inflated] if len(prompts_seen) == 1 else [HONEST]))

    monkeypatch.setattr(llm, "converse_json", fake)
    out = rewriter.tailor(resume, MATCH)
    assert out["bullets"] == [HONEST["text"]]
    assert "Do not use these words" in prompts_seen[1] and "production" in prompts_seen[1]


def test_tailor_removes_bullets_flagged_by_verifier(monkeypatch, resume):
    other = {"text": "Led a team of 3 engineers.", "source_quote": "Led a team of 3 engineers"}
    _patch_llm(
        monkeypatch,
        drafts=[draft([HONEST, other])] * 3,
        verdicts=[{"summary_supported": True, "unsupported_bullets": [1]}] * 3,
    )
    out = rewriter.tailor(resume, MATCH)
    assert out["bullets"] == [HONEST["text"]]


def test_tailor_fails_closed_when_nothing_is_supported(monkeypatch, resume):
    _patch_llm(monkeypatch, drafts=[draft([FAKE_QUOTE, FAKE_NUMBER])] * 3, verdicts=[])
    with pytest.raises(GuardrailError):
        rewriter.tailor(resume, MATCH)


def test_tailor_is_bounded(monkeypatch, resume):
    calls = []
    monkeypatch.setenv("MAX_AGENT_ITERATIONS", "2")

    def fake(system, user, validate, **_):
        calls.append(system[:20])
        return validate(draft([FAKE_QUOTE]))

    monkeypatch.setattr(llm, "converse_json", fake)
    with pytest.raises(GuardrailError):
        rewriter.tailor(resume, MATCH)
    assert len(calls) == 2


def test_handler_stores_pdf_marks_done_and_never_lists_gaps_as_bullets(monkeypatch, resume):
    stored, done, audit = {}, {}, []
    monkeypatch.setattr("common.jobs.set_stage", lambda *_: None)
    monkeypatch.setattr("common.jobs.write_audit", lambda j, s, o: audit.append(s))
    monkeypatch.setattr(storage, "read_inputs", lambda _id: (resume, "job"))
    monkeypatch.setattr(storage, "put_pdf", lambda k, d: stored.update({k: d}))
    monkeypatch.setattr(jobs, "mark_done", lambda j, r, k: done.update({"result": r, "key": k}))
    monkeypatch.setattr(jobs, "get_job", lambda _id: {"email": "me@example.com"})
    monkeypatch.setattr(jobs, "set_email_status", lambda j, s, m=None: done.update({"email_status": s}))
    sent = []
    monkeypatch.setattr(mailer, "send_result_email", lambda to, r, p: sent.append((to, r, p)) or ("SENT", None))
    _patch_llm(
        monkeypatch,
        drafts=[draft([HONEST], summary="Python engineer. token AKIAABCDEFGHIJKLMNOP")] * 3,
        verdicts=[{"summary_supported": True, "unsupported_bullets": []}] * 3,
    )
    monkeypatch.setattr(pdf, "build_pdf", lambda r: b"%PDF-fake")

    # summary contains a secret-like string: output guardrail must redact it
    out = rewriter.handler({"jobId": "j1", "analysis": {"requirements": REQS}, "match": MATCH})

    assert out["resultKey"] == "results/j1.pdf" == done["key"]
    assert stored["results/j1.pdf"] == b"%PDF-fake"
    assert "AKIA" not in json.dumps(done["result"])
    assert done["result"]["gaps"][0]["requirement"] == "Kubernetes"
    assert all("Kubernetes" not in b for b in done["result"]["bullets"])
    assert audit == ["rewriter"]
    # the emailed content is the same redacted result as the stored one, with the PDF attached
    assert sent[0][0] == "me@example.com"
    assert "AKIA" not in json.dumps(sent[0][1])
    assert sent[0][2] == b"%PDF-fake"
    assert done["email_status"] == "SENT" and out["emailStatus"] == "SENT"


def test_deliver_email_skips_without_address(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: {})
    assert rewriter.deliver_email("j1", {}, b"") == "SKIPPED"


def test_deliver_email_never_raises(monkeypatch):
    monkeypatch.setattr(jobs, "get_job", lambda _id: {"email": "me@example.com"})

    def boom(*_):
        raise RuntimeError("ses exploded")

    monkeypatch.setattr(mailer, "send_result_email", boom)
    assert rewriter.deliver_email("j1", {}, b"") == "FAILED"
