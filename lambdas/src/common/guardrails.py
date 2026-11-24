"""Input and output guardrails (Day-4 reliability + honesty rule)."""

import re
from typing import Any

from common import config
from common.errors import InputError

REDACTED = "[REDACTED]"

# Patterns for credentials that must never leave the pipeline.
_SECRET_PATTERNS = [
    re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[A-Z0-9]{16}\b"),  # AWS access key ids
    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S{20,}"),
    re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----|$)"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),  # generic API secret keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT
]


def validate_document(name: str, text: Any) -> str:
    """Return the trimmed document or raise InputError with a clear message."""
    if not isinstance(text, str) or not text.strip():
        raise InputError(f"The {name} is missing. Please provide both a resume and a job description.")
    cleaned = text.replace("\x00", "").strip()
    if len(cleaned) < config.min_doc_chars():
        raise InputError(f"The {name} is too short (minimum {config.min_doc_chars()} characters).")
    if len(cleaned) > config.max_doc_chars():
        raise InputError(f"The {name} is too long (maximum {config.max_doc_chars()} characters).")
    return cleaned


_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+"
)


def validate_email(value: Any) -> str:
    """Return a normalized email address or raise InputError. Rejects header-injection characters."""
    if not isinstance(value, str) or not value.strip():
        raise InputError("Please enter an email address to receive the result.")
    email = value.strip()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise InputError("Please enter a valid email address.")
    return email


def redact_secrets(text: str) -> str:
    """Replace anything that looks like a credential."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_secrets_deep(value: Any) -> Any:
    """Apply `redact_secrets` to every string inside a JSON-like structure."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_secrets_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_secrets_deep(v) for k, v in value.items()}
    return value


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


_NUMBER = re.compile(r"\d[\d,.]*")


def numbers_supported(text: str, source: str) -> bool:
    """True if every number in `text` also appears in `source` (blocks invented metrics)."""
    source_numbers = {n.rstrip(",.") for n in _NUMBER.findall(source)}
    return all(n.rstrip(",.") in source_numbers for n in _NUMBER.findall(text))


# Words that assert scope, seniority, ownership, proficiency or impact. The rewriter may only use
# one if the original resume uses it (or a word with the same stem) too.
CLAIM_TERMS = (
    "production",
    "managed",
    "manage",
    "led",
    "lead",
    "owned",
    "own",
    "architected",
    "architect",
    "spearheaded",
    "scaled",
    "scale",
    "scalable",
    "mentored",
    "mentor",
    "expert",
    "expertise",
    "proven",
    "track record",
    "extensive",
    "deep",
    "strong",
    "advanced",
    "senior",
    "principal",
    "enterprise",
    "mission-critical",
    "high-availability",
    "highly available",
    "millions",
    "thousands",
    "large-scale",
    "end-to-end",
    "full-stack",
    "improving",
    "improved",
    "increasing",
    "increased",
    "boosting",
    "enhancing",
    "streamline",
    "streamlined",
    "ensuring",
    "drove",
    "driving",
    "delivered",
    "delivering",
    "reliable",
    "robust",
    "confidence",
)
_WORD = re.compile(r"[A-Za-z][A-Za-z-]*")


def _stems(text: str) -> set[str]:
    """Stems of every word, plus the parts of hyphenated words ("Kubernetes-ready" -> kubernetes, ready)."""
    out = set()
    for word in _WORD.findall(text):
        out.add(_stem(word))
        if "-" in word:
            out.update(_stem(part) for part in word.split("-") if part)
    return out


def _stem(word: str) -> str:
    """Crude suffix stripping so "managed", "manages" and "managing" compare equal."""
    word = word.lower()
    stem = re.sub(r"(ing|ed|es|s|e)$", "", word)
    return stem if len(stem) >= 4 else word


def unsupported_claims(text: str, source: str) -> list[str]:
    """Claim terms used in `text` that the source never uses, compared on word stems."""
    text_stems, source_stems = _stems(text), _stems(source)
    text_lower, source_lower = text.lower(), source.lower()
    found, seen = [], set()
    for term in CLAIM_TERMS:
        if " " in term:
            if term in text_lower and term not in source_lower:
                found.append(term)
            continue
        stem = _stem(term)
        if stem in text_stems and stem not in source_stems and stem not in seen:
            seen.add(stem)
            found.append(term)
    return found


_GENERIC = {
    "experience",
    "strong",
    "knowledge",
    "ability",
    "familiarity",
    "understanding",
    "proficiency",
    "hands-on",
    "excellent",
    "good",
    "solid",
    "nice",
    "must",
    "have",
    "years",
    "year",
    "plus",
    "bonus",
    "preferred",
    "degree",
    "with",
    "and",
    "or",
    "the",
    "of",
    "in",
    "using",
    "working",
    "a",
    "an",
}


def gap_terms(gap_requirements: list[str], source: str) -> list[str]:
    """Distinctive terms (names, acronyms) from unmet requirements that the source never mentions.

    Example: gap "Experience with Kubernetes and Docker" on a resume without either -> ["Docker", "Kubernetes"].
    """
    source_stems = _stems(source)
    terms = set()
    for requirement in gap_requirements:
        for word in _WORD.findall(requirement):
            distinctive = word[0].isupper() or (len(word) >= 2 and word.isupper())
            if distinctive and word.lower() not in _GENERIC and _stem(word) not in source_stems:
                terms.add(word)
    return sorted(terms)


def mentions_any(text: str, terms: list[str]) -> list[str]:
    """Which of `terms` appear in `text` (stem match, case-insensitive)."""
    text_stems = _stems(text)
    return [t for t in terms if _stem(t) in text_stems]


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")


def quote_in_source(quote: str, source: str) -> bool:
    """True if `quote` appears verbatim (ignoring whitespace/case) in `source`.

    A quote may join several exact excerpts with "..."; every excerpt must then be in the source.
    Backbone of the honesty guardrail: any claim the model makes must point at text that really
    exists in the original resume.
    """
    src = _normalize(source)
    parts = [_normalize(p) for p in _ELLIPSIS.split(quote)]
    parts = [p.strip(" .;,") for p in parts if p.strip(" .;,")]
    return bool(parts) and all(len(p) >= 3 and p in src for p in parts)
