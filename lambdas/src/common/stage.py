"""Shared wrapper for Step Functions stage handlers.

Responsibilities: stage progress, audit logging, user-facing failure recording.
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

from common import jobs
from common.errors import GuardrailError, InputError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def stage_handler(stage: str) -> Callable:
    """Decorate `fn(event) -> dict`. The returned dict is the stage output."""

    def decorator(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable:
        @functools.wraps(fn)
        def wrapper(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
            job_id = event["jobId"]
            logger.info("stage=%s job=%s start", stage, job_id)
            jobs.set_stage(job_id, stage)
            try:
                output = fn(event)
            except (InputError, GuardrailError) as exc:
                # Non-retryable: record a clear message for the user before Step Functions catches it.
                jobs.mark_failed(job_id, exc.code, exc.user_message)
                logger.warning("stage=%s job=%s failed: %s", stage, job_id, exc.code)
                raise
            jobs.write_audit(job_id, stage, output)
            logger.info("stage=%s job=%s done", stage, job_id)
            return output

        return wrapper

    return decorator
