"""Storage error hierarchy."""


class StorageError(Exception):
    """Raised on read/write failures or persisted data corruption."""

    def __init__(self, message: str, *, corrupt: bool = False) -> None:
        super().__init__(message)
        self.corrupt = corrupt
