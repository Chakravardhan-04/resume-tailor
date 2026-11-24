import pytest

from common import guardrails
from common.errors import InputError


@pytest.mark.parametrize("text", [None, "", "short", "x" * 15_001])
def test_length_caps(text):
    with pytest.raises(InputError):
        guardrails.validate_document("resume", text)


@pytest.mark.parametrize(
    "secret", ["AKIAIOSFODNN7EXAMPLE", "ghp_" + "a" * 36, "sk-" + "a" * 30, "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.dozjgNryP4J3jVmN"]
)
def test_secrets_are_redacted(secret):
    assert guardrails.redact({"bullets": [f"key {secret}"]}) == {"bullets": ["key [REDACTED]"]}


def test_quote_must_be_in_the_resume(resume):
    assert guardrails.quote_in_source("built rest apis in python", resume)
    assert guardrails.quote_in_source("Built REST APIs ... using Lambda and DynamoDB", resume)
    assert not guardrails.quote_in_source("Managed Kubernetes clusters", resume)


def test_honesty_problems(resume):
    gaps = guardrails.gap_terms(["Experience with Kubernetes"], resume)
    assert gaps == ["Kubernetes"]
    assert guardrails.honesty_problems("Built APIs in Python.", resume, gaps) == []
    assert guardrails.honesty_problems("Led a team of 3.", resume, gaps) == []  # "Led" and "3" are in the resume
    assert guardrails.honesty_problems("Ran production Kubernetes.", resume, gaps) == ["production", "Kubernetes"]
    assert guardrails.honesty_problems("Grew revenue 40%.", resume, gaps) == ["numbers that are not in the resume"]
