import pytest

from common import guardrails
from common.errors import InputError


def test_validate_document_trims_and_accepts():
    assert guardrails.validate_document("resume", "  " + "a" * 60 + "  ") == "a" * 60


@pytest.mark.parametrize("value", [None, "", "   ", 123])
def test_validate_document_rejects_missing(value):
    with pytest.raises(InputError, match="missing"):
        guardrails.validate_document("resume", value)


def test_validate_document_rejects_too_short():
    with pytest.raises(InputError, match="too short"):
        guardrails.validate_document("job description", "hi")


def test_validate_document_rejects_too_long(monkeypatch):
    monkeypatch.setenv("MAX_DOC_CHARS", "100")
    with pytest.raises(InputError, match="too long"):
        guardrails.validate_document("resume", "x" * 101)


@pytest.mark.parametrize(
    "secret",
    [
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_" + "a" * 36,
        "xoxb-1234567890-abcdefghij",
        "sk-" + "a" * 30,
        "Bearer abcdefghijklmnopqrstuvwxyz123456",
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ],
)
def test_redact_secrets(secret):
    out = guardrails.redact_secrets(f"before {secret} after")
    assert secret not in out
    assert guardrails.REDACTED in out


def test_redact_secrets_leaves_normal_text():
    text = "Built APIs in Python and led a team of 3."
    assert guardrails.redact_secrets(text) == text


def test_redact_secrets_deep():
    data = {"a": ["AKIAIOSFODNN7EXAMPLE", {"b": "ok"}], "n": 1}
    out = guardrails.redact_secrets_deep(data)
    assert out["a"][0] == guardrails.REDACTED
    assert out["a"][1] == {"b": "ok"}
    assert out["n"] == 1


def test_quote_in_source_ignores_whitespace_and_case():
    src = "Built REST APIs in Python\n  and Flask"
    assert guardrails.quote_in_source("built rest apis in python and flask", src)


def test_quote_in_source_rejects_invented_text():
    assert not guardrails.quote_in_source("Managed Kubernetes clusters", "Built APIs in Python")


def test_quote_in_source_rejects_empty():
    assert not guardrails.quote_in_source("", "anything")


@pytest.mark.parametrize(
    ("text", "source", "expected"),
    [
        ("Managed the platform", "I manage a platform", []),  # same stem
        ("Managing teams", "Built APIs", ["managed"]),
        ("Led the migration", "Led a team", []),
        ("Ran production systems", "Ran systems", ["production"]),
        ("Proven track record of delivery", "Shipped features", ["proven", "track record"]),
        ("Built APIs in Python", "Built APIs in Python", []),
    ],
)
def test_unsupported_claims(text, source, expected):
    assert guardrails.unsupported_claims(text, source) == expected
