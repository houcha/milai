# Contract: StorageClient

**File**: `src/milai/storage/client.py`
**Type**: Python `Protocol` (structural subtyping)
**Purpose**: Abstract local persistence so state handlers never reference file paths or JSON serialisation directly. Satisfies Constitution Principle V for the storage dependency.

---

## Protocol Definition

One storage protocol owns the atomic v1 snapshot:

```python
from typing import Protocol
from milai.models.state import PersistedState

class StorageClient(Protocol):
    async def load(self) -> PersistedState | None:
        """
        Load and return the persisted application snapshot, or None if no state
        exists yet (first run). Raises StorageError if the file exists but is
        corrupt/invalid.
        """

    async def save(self, state: PersistedState) -> None:
        """
        Atomically persist PersistedState (`UserState` + `AppState`). Raises
        StorageError on write failure. Must be safe to call after every state
        transition (frequent writes).
        """

    async def delete(self) -> None:
        """
        Delete the persisted state (user-initiated reset). No-op if no state exists.
        Raises StorageError on failure.
        """
```

---

## Exceptions

```python
# src/milai/storage/errors.py

class StorageError(Exception):
    """Raised on read/write failures or data corruption."""
    def __init__(self, message: str, *, corrupt: bool = False):
        super().__init__(message)
        self.corrupt = corrupt  # True = data exists but is unreadable; offer recovery
```

---

## Contract Rules

1. **`save` is atomic**: write to a temp file in the same directory, then `os.replace`. A crash mid-write must never leave the state file in a partially-written state.
2. **`load` returns `None` (not raises) for a missing file**: callers treat `None` as "first run".
3. **`load` raises `StorageError(corrupt=True)` for a present-but-invalid file**: callers handle this by offering the user a recovery prompt (backup + fresh start).
4. **`delete` is a no-op for a missing file**: idempotent.
5. **All methods are `async`**: even though local file I/O is synchronous, the protocol is async so a future networked implementation (e.g., cloud sync in v3) is a drop-in.
6. **`PersistedState` is the persistence unit**: workflow resume depends on persisting both `UserState` and `AppState` together after each transition.

---

## Concrete Implementations

```python
# src/milai/storage/local.py

class LocalStorage:
    """
    Stores PersistedState as JSON at ~/.milai/state.json.
    Atomic writes via tempfile + os.replace.
    """
    DEFAULT_PATH = Path.home() / ".milai" / "state.json"

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self._path = path

    async def load(self) -> PersistedState | None: ...
    async def save(self, state: PersistedState) -> None: ...
    async def delete(self) -> None: ...
```

`LocalStorage` accepts a `path` parameter so tests can use `tmp_path` without touching `~/.milai`.

---

## Test Doubles

```python
# tests/fakes/storage_client.py

class InMemoryStorage:
    def __init__(self, initial: PersistedState | None = None):
        self._state = initial
        self.save_count = 0

    async def load(self) -> PersistedState | None:
        return self._state

    async def save(self, state: PersistedState) -> None:
        self._state = state
        self.save_count += 1

    async def delete(self) -> None:
        self._state = None
```

---

## Implementations

| Version | Implementation class | Location |
|---|---|---|
| v1 state | `LocalStorage` | `src/milai/storage/local.py` |
| Tests state | `InMemoryStorage` | `tests/fakes/storage_client.py` |
