import pytest

from scorer import handler as scorer

REQS = [
    {"id": "R1", "text": "Python", "category": "must_have", "type": "skill"},
    {"id": "R2", "text": "AWS Lambda", "category": "must_have", "type": "skill"},
    {"id": "R3", "text": "Kubernetes", "category": "nice_to_have", "type": "skill"},
]


def test_validator_requires_every_id_exactly_once():
    validate = scorer.make_validator({"R1", "R2"})
    ok = {"matched": [{"id": "R1", "evidence": "x"}], "gaps": [{"id": "R2", "reason": "y"}]}
    assert validate(ok) == ok
    with pytest.raises(ValueError, match="missing"):
        validate({"matched": [{"id": "R1"}], "gaps": []})
    with pytest.raises(ValueError, match="unknown"):
        validate({"matched": [{"id": "R9"}], "gaps": [{"id": "R1"}, {"id": "R2"}]})
    with pytest.raises(ValueError, match="exactly once"):
        validate({"matched": [{"id": "R1"}, {"id": "R1"}], "gaps": [{"id": "R2"}]})


def test_score_is_weighted_and_deterministic(resume):
    judgement = {
        "matched": [
            {"id": "R1", "evidence": "Built REST APIs in Python and Flask"},
            {"id": "R2", "evidence": "Deployed services to AWS using Lambda and DynamoDB"},
        ],
        "gaps": [{"id": "R3", "reason": "Not mentioned"}],
    }
    out = scorer.score_match(REQS, judgement, resume)
    assert out["score"] == 80  # (2 + 2) / (2 + 2 + 1)
    assert [g["requirement"] for g in out["gaps"]] == ["Kubernetes"]


def test_fabricated_evidence_is_downgraded_to_gap(resume):
    judgement = {
        "matched": [
            {"id": "R1", "evidence": "Built REST APIs in Python and Flask"},
            {"id": "R2", "evidence": "Architected serverless AWS Lambda platform"},  # not in resume
            {"id": "R3", "evidence": ""},  # no evidence
        ],
        "gaps": [],
    }
    out = scorer.score_match(REQS, judgement, resume)
    assert {m["id"] for m in out["matched"]} == {"R1"}
    assert {g["id"] for g in out["gaps"]} == {"R2", "R3"}
    assert out["score"] == 40  # 2 / 5
