"""Local JSON storage for learning sessions."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from milai.models.session import LearningSession
from milai.storage.errors import StorageError


class LocalStorage:
    """Store the full learning session in a single JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self) -> LearningSession | None:
        if not self._path.exists():
            return None
        try:
            raw = self._path.read_text()
            data = json.loads(raw)
            if not isinstance(data, dict) or "id" not in data:
                raise ValueError("learning session is missing required id")
            return LearningSession.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise StorageError(
                f"could not load learning session from {self._path}: {exc}",
                corrupt=True,
            ) from exc

    async def save(self, state: LearningSession) -> None:
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
            msg = f"could not save learning session to {self._path}: {exc}"
            raise StorageError(msg) from exc

    async def delete(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            msg = f"could not delete learning session at {self._path}: {exc}"
            raise StorageError(msg) from exc


JsonData = dict[str, Any]
