"""Local JSON storage for persisted snapshots."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from milai.models.state import PersistedState
from milai.storage.errors import StorageError


class LocalStorage:
    """Store the full app snapshot in a single JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self) -> PersistedState | None:
        if not self._path.exists():
            return None
        try:
            return PersistedState.model_validate_json(self._path.read_text())
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise StorageError(
                f"could not load persisted state from {self._path}: {exc}",
                corrupt=True,
            ) from exc

    async def save(self, state: PersistedState) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = state.model_dump_json(indent=2)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"{self._path.name}.",
                suffix=".tmp",
                dir=self._path.parent,
                text=True,
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                    tmp_file.write(payload)
                    tmp_file.write("\n")
                os.replace(tmp_path, self._path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        except OSError as exc:
            msg = f"could not save persisted state to {self._path}: {exc}"
            raise StorageError(msg) from exc

    async def delete(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            msg = f"could not delete persisted state at {self._path}: {exc}"
            raise StorageError(msg) from exc


JsonData = dict[str, Any]
