"""Learning session model."""

from uuid import uuid4

from pydantic import BaseModel, Field

from milai.models.user_state import UserState
from milai.state.variants import AppState


class LearningSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user: UserState
    app: AppState
