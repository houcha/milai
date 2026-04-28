"""Persisted application snapshot model."""

from pydantic import BaseModel

from milai.models.user_state import UserState
from milai.state.variants import AppState


class PersistedState(BaseModel):
    user: UserState
    app: AppState
