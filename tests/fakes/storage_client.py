"""In-memory StorageClient test double."""

from milai.models.state import PersistedState


class InMemoryStorage:
    def __init__(self, initial: PersistedState | None = None) -> None:
        self._state = initial
        self.save_count = 0

    async def load(self) -> PersistedState | None:
        return self._state

    async def save(self, state: PersistedState) -> None:
        self._state = state
        self.save_count += 1

    async def delete(self) -> None:
        self._state = None
