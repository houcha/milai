# Contract: LLMClient

**File**: `src/milai/llm/client.py`
**Type**: Python `Protocol` (structural subtyping)
**Purpose**: Mediate all LLM calls through a single interface. State handlers and prompt builders never import `litellm` directly — they call through `LLMClient`. This makes the LLM provider a configuration choice, enables test doubles, and satisfies Constitution Principle V.

---

## Protocol Definition

```python
from typing import Protocol, TypeVar
from pydantic import BaseModel
from milai.llm.types import Message

T = TypeVar("T", bound=BaseModel)

class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        response_model: type[T],
    ) -> T:
        """
        Send a list of messages and parse the response into `response_model`.
        Raises LLMError on API failure.
        Raises LLMParseError if the response cannot be validated against the model.
        """

    async def chat(
        self,
        messages: list[Message],
    ) -> str:
        """
        Send a list of messages and return the raw assistant text response.
        Used for free-form deviation mode where structured output is not needed.
        Raises LLMError on API failure.
        """
```

---

## Supporting Types

```python
# src/milai/llm/types.py

from dataclasses import dataclass
from enum import Enum

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

@dataclass
class Message:
    role: Role
    content: str
```

---

## Exceptions

```python
# src/milai/llm/errors.py

class LLMError(Exception):
    """Raised when the LLM provider returns an error or is unreachable."""
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable

class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed into the expected schema."""
    def __init__(self, message: str, raw_response: str):
        super().__init__(message, retryable=True)
        self.raw_response = raw_response
```

`retryable=True` tells the state machine handler to offer the user a retry prompt (FR-013). `retryable=False` is reserved for hard failures (e.g., invalid API key, quota exhausted) where retrying is pointless.

---

## Contract Rules

1. **Both methods are `async`**: implementations must not block the event loop.
2. **`complete` MUST raise `LLMParseError` (not return `None`) if the response fails schema validation**: callers depend on receiving a typed object or an exception — never an untyped partial result.
3. **`chat` MUST return a non-empty string**: if the model returns an empty response, raise `LLMError`.
4. **No retry logic inside the implementation**: retries are the caller's responsibility (state machine handlers). The implementation makes exactly one attempt per call.
5. **No conversation state stored in the client**: all prompt context is in the `messages` list. A client instance stores only its resolved model profile configuration and may be reused by any handlers assigned to that profile.
6. **API keys are resolved by the provider layer from environment variables only**: secrets never appear in config files or persisted state.
7. **Each client instance represents exactly one resolved LLM profile**: model, temperature, top_p, and max_tokens are fixed at construction time. The client does not know about app states, profile names, or routing tables.
8. **Profile selection happens outside `LLMClient`**: the entrypoint builds one `LLMClient` per configured profile, chooses the profile for each state from config, and passes the resolved client into that state's handler constructor. Profile references are validated at startup.

---

## Concrete Implementation (LiteLLM)

```python
# src/milai/llm/litellm_client.py

from milai.config import LLMConfig

class LiteLLMClient:
    """
    Concrete LLMClient backed by LiteLLM.
    Receives one fully-resolved LLMConfig for a single profile.
    API keys are resolved by LiteLLM from environment variables automatically.
    """
    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    async def complete(self, messages, *, response_model):
        # calls litellm.acompletion with response_format={"type": "json_object"}
        # parses result with response_model.model_validate_json(...)
        # wraps provider errors as LLMError, parse failures as LLMParseError
        ...

    async def chat(self, messages) -> str:
        # calls litellm.acompletion without structured output
        # returns assistant message content
        ...
```

---

## Test Double

```python
# tests/fakes/llm_client.py

class ScriptedLLMClient:
    """
    Deterministic test double. Feed it a list of scripted responses;
    it returns them in order. Supports both structured and chat responses.
    """
    def __init__(self, responses: list[BaseModel | str | Exception]):
        self._responses = iter(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, messages, *, response_model):
        self.calls.append(messages)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return result

    async def chat(self, messages) -> str:
        self.calls.append(messages)
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return str(result)
```

---

## Implementations

| Version | Implementation class | Location |
|---|---|---|
| v1 | `LiteLLMClient` | `src/milai/llm/litellm_client.py` |
| Tests | `ScriptedLLMClient` | `tests/fakes/llm_client.py` |
