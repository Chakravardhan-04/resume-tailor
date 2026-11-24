"""Wrapper shared by the three Step Functions stages: progress, audit log, clear failures."""

import functools

from common import aws
from common.errors import GuardrailError, InputError


def stage(name: str):
    def decorate(run):
        @functools.wraps(run)
        def handler(event: dict, _context=None) -> dict:
            job_id = event["jobId"]
            print(f"stage={name} job={job_id} start")
            aws.set_stage(job_id, name)  # the page shows which stage is running
            try:
                output = run(event)
            except (InputError, GuardrailError) as exc:
                aws.mark_failed(job_id, exc.code, exc.message)  # record a clear message, then let Catch fire
                raise
            aws.write_audit(job_id, name, output)  # audit log: every stage's output, by job id
            print(f"stage={name} job={job_id} done")
            return output  # Step Functions stores this in the state ($.analysis / $.match / $.rewrite)

        return handler

    return decorate
