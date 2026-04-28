"""Protocol for persisted snapshot storage."""

from typing import Protocol

from milai.models.state import PersistedState


class StorageClient(Protocol):
    async def load(self) -> PersistedState | None:
        """Load the persisted snapshot, or None if it does not exist."""

    async def save(self, state: PersistedState) -> None:
        """Persist the snapshot atomically."""

    async def delete(self) -> None:
        """Delete persisted state if it exists."""
