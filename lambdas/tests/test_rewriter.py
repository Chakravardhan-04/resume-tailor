from rewriter import handler as rewriter

MATCH = {
    "score": 80,
    "matched": [{"requirement": "Python", "category": "must_have", "evidence": "Built REST APIs in Python and Flask"}],
    "gaps": [{"requirement": "Experience with Kubernetes", "category": "nice_to_have", "reason": "Not in resume"}],
}
HONEST = {"text": "Built Python and Flask REST APIs serving 2M requests per day.", "source_quote": "REST APIs in Python and Flask"}


def fake_agents(monkeypatch, drafts):
    """Fake the rewriter agent (returns `drafts` in turn) and a verifier that approves everything."""
    drafts = iter(drafts)

    def fake(agent, system, user, tool, max_turns=3):
        if agent == "verifier":
            return {"summary_supported": True, "unsupported_bullets": []}
        return tool.validate(next(drafts))

    monkeypatch.setattr(rewriter, "run_agent", fake)


def test_jd_demanding_an_absent_skill_puts_it_in_gaps_never_in_bullets(monkeypatch, resume):
    """Honesty acceptance test: the job wants Kubernetes, the resume has none, the model keeps adding it."""
    fabricated = {"text": "Deployed services to AWS and Kubernetes.", "source_quote": "Deployed services to AWS"}
    invented_quote = {"text": "Ran Kubernetes clusters.", "source_quote": "Ran Kubernetes clusters"}
    draft = {"summary": "Python engineer, Kubernetes-ready.", "bullets": [HONEST, fabricated, invented_quote]}
    fake_agents(monkeypatch, [draft] * 3)

    out = rewriter.tailor(resume, MATCH)

    assert out["bullets"] == [HONEST["text"]]  # only the honest bullet survives
    assert out["summary"] == "Built REST APIs in Python and Flask"  # summary fell back to verbatim resume text
    assert "kubernetes" not in " ".join(out["bullets"] + [out["summary"]]).lower()


def test_nothing_honest_fails_closed(monkeypatch, resume):
    import pytest

    from common.errors import GuardrailError

    fake_agents(monkeypatch, [{"summary": "Expert.", "bullets": [{"text": "Ran Kubernetes.", "source_quote": "nope"}]}] * 3)
    with pytest.raises(GuardrailError):
        rewriter.tailor(resume, MATCH)
