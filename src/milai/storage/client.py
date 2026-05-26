"""Protocol for persisted snapshot storage."""

from typing import Protocol

from milai.models.session import LearningSession


class StorageClient(Protocol):
    async def load(self) -> LearningSession | None:
        """Load the persisted snapshot, or None if it does not exist."""

    async def save(self, state: LearningSession) -> None:
        """Persist the snapshot atomically."""

    async def delete(self) -> None:
        """Delete the learning session if it exists."""
