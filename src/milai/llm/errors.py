"""LLM error hierarchy."""


class LLMError(Exception):
    """Raised when the LLM provider returns an error or is unreachable."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMParseError(LLMError):
    """Raised when an LLM response cannot be parsed into the expected schema."""

    def __init__(self, message: str, raw_response: str) -> None:
        super().__init__(message, retryable=True)
        self.raw_response = raw_response
