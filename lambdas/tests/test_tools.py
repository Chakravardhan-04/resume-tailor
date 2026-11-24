import pytest
from conftest import tool_call

from common import aws, tools
from common.errors import InputError

KEYS = {"resume_key": "uploads/j1/resume.txt", "job_key": "uploads/j1/job.txt"}
JOB = "We need a Backend Engineer. Must have: Python, AWS Lambda. Nice to have: Kubernetes."
REQS = [
    {"id": "R1", "text": "Python", "category": "must_have"},
    {"id": "R2", "text": "AWS Lambda", "category": "must_have"},
    {"id": "R3", "text": "Kubernetes", "category": "nice_to_have"},
]


def test_read_inputs_loads_both_documents(fake_aws, resume):
    fake_aws["files"].update({KEYS["resume_key"]: resume, KEYS["job_key"]: JOB})
    assert tools.read_inputs(**KEYS) == {"resume_text": resume.strip(), "job_text": JOB}


def test_missing_document_escalates_with_a_clear_message(fake_aws, resume):
    fake_aws["files"][KEYS["resume_key"]] = resume  # job description never uploaded
    with pytest.raises(InputError, match="job description is missing"):
        tools.read_inputs(**KEYS)


def test_missing_input_field_escalates():
    with pytest.raises(InputError, match="'job_key' is missing"):
        tools.read_inputs(KEYS["resume_key"], None)
    with pytest.raises(InputError, match="'requirements' is missing"):
        tools.score_match("resume", [])


def test_length_cap(fake_aws, resume):
    fake_aws["files"].update({KEYS["resume_key"]: resume, KEYS["job_key"]: "x" * 15_001})
    with pytest.raises(InputError, match="too long"):
        tools.read_inputs(**KEYS)


def test_extract_requirements_assigns_ids(fake_aws, monkeypatch):
    reply = {"requirements": [{"text": "Python", "category": "must_have"}, {"text": "Kubernetes", "category": "nice_to_have"}]}
    monkeypatch.setattr(aws, "converse", lambda *a: tool_call("submit_requirements", reply))
    out = tools.extract_requirements(JOB)
    assert [r["id"] for r in out["requirements"]] == ["R1", "R2"]


def test_score_match_rejects_invented_evidence_then_scores_in_code(fake_aws, monkeypatch, resume):
    replies = iter(
        [
            # turn 1: claims Lambda evidence that is not in the resume -> rejected and sent back
            tool_call(
                "submit_judgement",
                {
                    "matched": [
                        {"id": "R1", "evidence": "Built REST APIs in Python"},
                        {"id": "R2", "evidence": "Architected Lambda platforms"},
                    ],
                    "gaps": [{"id": "R3", "reason": "Not mentioned"}],
                },
            ),
            # turn 2: corrected
            tool_call(
                "submit_judgement",
                {
                    "matched": [
                        {"id": "R1", "evidence": "Built REST APIs in Python"},
                        {"id": "R2", "evidence": "Deployed services to AWS using Lambda"},
                    ],
                    "gaps": [{"id": "R3", "reason": "Not mentioned"}],
                },
            ),
        ]
    )
    monkeypatch.setattr(aws, "converse", lambda *a: next(replies))
    out = tools.score_match(resume, REQS)
    assert out["score"] == 80  # (2 + 2) / (2 + 2 + 1)
    assert [g["requirement"] for g in out["gaps"]] == ["Kubernetes"]
