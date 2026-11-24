"""Error types. Step Functions matches Retry/Catch rules on these class names (see infra/lib/constructs/pipeline.ts)."""


class PipelineError(Exception):
    code = "PipelineError"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message  # safe to show to the user


class InputError(PipelineError):
    """Missing or invalid input (e.g. no job description). Not retried: the job fails with this message."""

    code = "InputError"


class GuardrailError(PipelineError):
    """The honesty guardrail left nothing truthful to return. Not retried."""

    code = "GuardrailError"


class ThrottledError(PipelineError):
    """Bedrock is busy. Step Functions retries this with backoff."""

    code = "ThrottledError"


class ModelOutputError(PipelineError):
    """The agent loop hit its turn limit without a valid answer. Step Functions retries this."""

    code = "ModelOutputError"
