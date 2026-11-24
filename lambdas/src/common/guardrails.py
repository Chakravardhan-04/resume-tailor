"""Guardrails.

Input:   length caps on both documents.
Output:  redact anything that looks like a secret.
Honesty: checks the rewriter's text against the original resume (used by rewriter/handler.py).
"""

import re
from typing import Any

from common.errors import InputError

MIN_CHARS, MAX_CHARS = 50, 15_000  # length cap for each document

# ---------------------------------------------------------------- input


def validate_document(name: str, text: Any) -> str:
    """Return the trimmed document, or raise InputError with a message for the user."""
    if not isinstance(text, str) or not text.strip():
        raise InputError(f"The {name} is missing. Please provide both a resume and a job description.")
    text = text.strip()
    if len(text) < MIN_CHARS:
        raise InputError(f"The {name} is too short (minimum {MIN_CHARS} characters).")
    if len(text) > MAX_CHARS:
        raise InputError(f"The {name} is too long (maximum {MAX_CHARS} characters).")
    return text


# ---------------------------------------------------------------- output: no leaked secrets

SECRET_PATTERNS = [
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),  # AWS access key id
    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S{20,}"),  # AWS secret key
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"),  # private keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub tokens
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),  # API secret keys
    re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}\b"),  # JWTs
]


def redact(value: Any) -> Any:
    """Replace secret-looking strings anywhere inside a JSON-like value."""
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- honesty

# Words that claim scope, seniority, skill level or impact. The rewriter may only use one if the resume does.
CLAIM_WORDS = {
    "production",
    "managed",
    "led",
    "owned",
    "architected",
    "spearheaded",
    "scaled",
    "scalable",
    "mentored",
    "expert",
    "expertise",
    "proven",
    "extensive",
    "deep",
    "strong",
    "advanced",
    "senior",
    "enterprise",
    "robust",
    "reliable",
    "improving",
    "improved",
    "increasing",
    "increased",
    "boosting",
    "enhancing",
    "streamlined",
    "delivered",
    "driving",
    "drove",
    "ensuring",
    "confidence",
    "millions",
    "thousands",
}
CLAIM_PHRASES = {"track record", "at scale", "large-scale", "end-to-end", "mission-critical"}
GENERIC_WORDS = {"experience", "with", "and", "or", "of", "in", "the", "a", "an", "using", "years", "strong", "hands-on"}

WORD = re.compile(r"[A-Za-z][A-Za-z-]*")
NUMBER = re.compile(r"\d[\d,.]*")


def stem(word: str) -> str:
    """Crude stemming so "managed", "manages" and "managing" compare equal."""
    word = word.lower()
    short = re.sub(r"(ing|ed|es|s|e)$", "", word)
    return short if len(short) >= 4 else word


def stems(text: str) -> set[str]:
    words = WORD.findall(text)
    parts = [p for w in words for p in w.split("-") if p]  # "Kubernetes-ready" -> kubernetes, ready
    return {stem(w) for w in words + parts}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_source(quote: str, source: str) -> bool:
    """True if every '...'-separated part of `quote` appears word for word in the resume."""
    parts = [normalize(p).strip(" .;,") for p in re.split(r"\.{3,}|…", quote)]
    parts = [p for p in parts if p]
    return bool(parts) and all(len(p) >= 3 and p in normalize(source) for p in parts)


def unsupported_numbers(text: str, source: str) -> bool:
    """True if `text` has a number the resume does not contain (an invented metric)."""
    known = {n.rstrip(",.") for n in NUMBER.findall(source)}
    return any(n.rstrip(",.") not in known for n in NUMBER.findall(text))


def unsupported_claims(text: str, source: str) -> list[str]:
    """Claim words/phrases in `text` that the resume never uses."""
    text_stems, source_stems = stems(text), stems(source)
    words = sorted(w for w in CLAIM_WORDS if stem(w) in text_stems and stem(w) not in source_stems)
    phrases = sorted(p for p in CLAIM_PHRASES if p in text.lower() and p not in source.lower())
    return words + phrases


def gap_terms(gap_requirements: list[str], source: str) -> list[str]:
    """Distinctive words from unmet requirements that the resume lacks, e.g. "Kubernetes", "Terraform"."""
    source_stems = stems(source)
    terms = {
        w
        for req in gap_requirements
        for w in WORD.findall(req)
        if w[0].isupper() and w.lower() not in GENERIC_WORDS and stem(w) not in source_stems
    }
    return sorted(terms)


def honesty_problems(text: str, source: str, gap_words: list[str]) -> list[str]:
    """Everything in `text` the resume does not support. An empty list means the text is honest."""
    found = unsupported_claims(text, source)
    found += [t for t in gap_words if stem(t) in stems(text)]  # never mention a gap skill
    if unsupported_numbers(text, source):
        found.append("numbers that are not in the resume")
    return found
