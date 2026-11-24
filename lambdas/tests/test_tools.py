import pytest
from botocore.exceptions import ClientError

from common import storage, tools
from common.errors import InputError

REQS = [
    {"id": "R1", "text": "Python", "category": "must_have", "type": "skill"},
    {"id": "R2", "text": "AWS Lambda", "category": "must_have", "type": "skill"},
    {"id": "R3", "text": "Kubernetes", "category": "nice_to_have", "type": "skill"},
]
KEYS = {"resume_key": "uploads/j1/resume.txt", "job_key": "uploads/j1/job.txt"}


# ---- specs match the project spec exactly


@pytest.mark.parametrize(
    ("fn", "fields"),
    [
        (tools.read_inputs, ["resume_key", "job_key"]),
        (tools.extract_requirements, ["job_text"]),
        (tools.score_match, ["resume_text", "requirements"]),
    ],
)
def test_tool_specs_match_the_project_spec(fn, fields):
    spec = fn.spec
    assert spec.name == fn.__name__
    assert len(spec.description) > 60
    assert spec.input_schema["required"] == fields
    assert list(spec.input_schema["properties"]) == fields
    for field in fields:
        assert spec.input_schema["properties"][field]["description"]


# ---- read_inputs


def fake_s3(monkeypatch, objects):
    def get_text(key):
        if key not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return objects[key]

    monkeypatch.setattr(storage, "get_text", get_text)


def test_read_inputs_loads_both_documents(monkeypatch, resume, job):
    fake_s3(monkeypatch, {KEYS["resume_key"]: resume, KEYS["job_key"]: job})
    out = tools.read_inputs(**KEYS)
    assert out == {"resume_text": resume.strip(), "job_text": job.strip()}


@pytest.mark.parametrize("missing", ["resume_key", "job_key"])
def test_read_inputs_escalates_when_an_argument_is_missing(missing):
    args = {**KEYS, missing: None}
    with pytest.raises(InputError, match=f"'{missing}' is missing"):
        tools.read_inputs(**args)


def test_read_inputs_escalates_when_a_document_is_missing(monkeypatch, resume):
    fake_s3(monkeypatch, {KEYS["resume_key"]: resume})
    with pytest.raises(InputError, match="job description is missing"):
        tools.read_inputs(**KEYS)


def test_read_inputs_applies_length_caps(monkeypatch, resume):
    monkeypatch.setenv("MAX_DOC_CHARS", "100")
    fake_s3(monkeypatch, {KEYS["resume_key"]: resume, KEYS["job_key"]: "x" * 101})
    with pytest.raises(InputError, match="too long"):
        tools.read_inputs(**KEYS)


def test_read_inputs_rejects_keys_outside_uploads():
    with pytest.raises(InputError, match="invalid"):
        tools.read_inputs(resume_key="results/other.pdf", job_key=KEYS["job_key"])


# ---- extract_requirements


def test_extract_requirements_validates_and_renumbers(monkeypatch, job):
    def fake_agent(agent, system, user, answer, **_):
        assert agent == "analyzer" and job in user and answer.name == "submit_requirements"
        return answer.validate(
            {
                "requirements": [
                    {"text": "Python", "category": "must_have", "type": "skill"},
                    {"text": "Kubernetes", "category": "nice_to_have", "type": "bogus"},
                ]
            }
        )

    monkeypatch.setattr(tools, "run_agent", fake_agent)
    out = tools.extract_requirements(job_text=job)
    assert [r["id"] for r in out["requirements"]] == ["R1", "R2"]
    assert out["requirements"][1]["type"] == "other"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"requirements": []},
        {"requirements": [{"text": "", "category": "must_have"}]},
        {"requirements": [{"text": "x", "category": "weird"}]},
    ],
)
def test_validate_requirements_rejects_bad_shapes(data):
    with pytest.raises(ValueError):
        tools.validate_requirements(data)


def test_extract_requirements_escalates_on_empty_input():
    with pytest.raises(InputError, match="job_text"):
        tools.extract_requirements(job_text="  ")


# ---- score_match


def test_judgement_validator_requires_every_id_exactly_once():
    validate = tools.make_judgement_validator({"R1", "R2"}, "Built APIs in Python.")
    ok = {"matched": [{"id": "R1", "evidence": "Built APIs"}], "gaps": [{"id": "R2", "reason": "y"}]}
    assert validate(ok) == ok
    with pytest.raises(ValueError, match="missing"):
        validate({"matched": [{"id": "R1"}], "gaps": []})
    with pytest.raises(ValueError, match="unknown"):
        validate({"matched": [{"id": "R9"}], "gaps": [{"id": "R1"}, {"id": "R2"}]})
    with pytest.raises(ValueError, match="exactly once"):
        validate({"matched": [{"id": "R1"}, {"id": "R1"}], "gaps": [{"id": "R2"}]})


def test_judgement_validator_sends_non_verbatim_evidence_back(resume):
    validate = tools.make_judgement_validator({"R1", "R2"}, resume)
    joined = {"id": "R1", "evidence": "Built REST APIs in Python ... Deployed services to AWS"}
    with pytest.raises(ValueError, match=r"\['R2'\] is not copied verbatim"):
        validate({"matched": [joined, {"id": "R2", "evidence": "Ran Lambda at scale"}], "gaps": []})
    assert validate({"matched": [joined], "gaps": [{"id": "R2", "reason": "no"}]})


def test_score_is_weighted_and_fabricated_evidence_becomes_a_gap(monkeypatch, resume):
    def fake_agent(agent, system, user, answer, **_):
        assert agent == "scorer" and answer.name == "submit_judgement"
        # bypass the validator to exercise the scoring safety net directly
        return {
            "matched": [
                {"id": "R1", "evidence": "Built REST APIs in Python and Flask"},
                {"id": "R2", "evidence": "Architected a serverless AWS Lambda platform"},  # not in resume
            ],
            "gaps": [{"id": "R3", "reason": "Not mentioned"}],
        }

    monkeypatch.setattr(tools, "run_agent", fake_agent)
    out = tools.score_match(resume_text=resume, requirements=REQS)
    assert {m["id"] for m in out["matched"]} == {"R1"}
    assert {g["id"] for g in out["gaps"]} == {"R2", "R3"}
    assert out["score"] == 40  # 2 / (2 + 2 + 1)


def test_score_match_escalates_without_requirements(resume):
    with pytest.raises(InputError, match="requirements"):
        tools.score_match(resume_text=resume, requirements=[])
