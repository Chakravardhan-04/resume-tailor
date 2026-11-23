"""Error types shared by all stages.

Step Functions matches Retry/Catch rules on the exception class name, so these
names are part of the contract with the state machine (see infra/).
"""


class PipelineError(Exception):
    """Base class. `user_message` is safe to show to the end user."""

    code = "PipelineError"

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class InputError(PipelineError):
    """Missing or invalid user input. Not retryable."""

    code = "InputError"


class GuardrailError(PipelineError):
    """A guardrail rejected the content (e.g. nothing honest left to say). Not retryable."""

    code = "GuardrailError"


class ThrottledError(PipelineError):
    """Transient model/service pressure. Retryable by Step Functions."""

    code = "ThrottledError"


class ModelOutputError(PipelineError):
    """Model never produced valid output within the bounded loop. Retryable once."""

    code = "ModelOutputError"
