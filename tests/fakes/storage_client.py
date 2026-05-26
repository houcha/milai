"""In-memory StorageClient test double."""

from milai.models.session import LearningSession


class InMemoryStorage:
    def __init__(self, initial: LearningSession | None = None) -> None:
        self._state = initial
        self.save_count = 0

    async def load(self) -> LearningSession | None:
        return self._state

    async def save(self, state: LearningSession) -> None:
        self._state = state
        self.save_count += 1

    async def delete(self) -> None:
        self._state = None
