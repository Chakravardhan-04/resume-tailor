"""HTTP API (payload v2) helpers."""

import json
from typing import Any

_HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": _HEADERS, "body": json.dumps(body)}


def parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON object body or raise ValueError."""
    raw = event.get("body")
    if event.get("isBase64Encoded") and raw:
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw or "")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


class Unauthorized(Exception):
    """The request carries no usable identity."""


def caller(event: dict[str, Any]) -> tuple[str, str]:
    """Return (user id, verified email) from the JWT claims API Gateway already validated."""
    claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email or str(claims.get("email_verified")).lower() != "true":
        raise Unauthorized("A verified account email is required.")
    return str(sub), str(email)
