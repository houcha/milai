"""Onboarding state handler."""

from milai.io.mediator import IOMediator
from milai.io.types import ContentKind, RichContent
from milai.models.user_state import PreferenceMap, UserProfile, UserState
from milai.state.variants import AppState, AssessmentState, OnboardingState


class OnboardingHandler:
    def __init__(self, mediator: IOMediator) -> None:
        self._mediator = mediator

    async def step(
        self, app: AppState, user: UserState
    ) -> tuple[AssessmentState, UserState]:
        if not isinstance(app, OnboardingState):
            raise TypeError(f"OnboardingHandler cannot handle {app.type!r}")
        await self._mediator.clear()
        await self._mediator.show(
            RichContent("Language setup", kind=ContentKind.HEADER)
        )

        target_language = await self._prompt_required(
            "Target language", error="Target language is required."
        )
        native_language = await self._prompt_optional("Native language")
        learning_goal = await self._prompt_optional("Learning goal")
        minutes_per_day = await self._prompt_minutes()
        preferences = _parse_preferences(
            await self._mediator.prompt(
                "Teaching preferences",
                placeholder="formality=casual, avoid=grammar jargon",
            )
        )

        updated = user.model_copy(deep=True)
        updated.profile = UserProfile(
            target_language=target_language,
            native_language=native_language,
            learning_goal=learning_goal,
            minutes_per_day=minutes_per_day,
            preferences=preferences,
        )
        return AssessmentState(), updated

    async def _prompt_required(self, label: str, *, error: str) -> str:
        while True:
            value = await self._mediator.prompt(label)
            if value:
                return value
            await self._mediator.show_error(error)

    async def _prompt_optional(self, label: str) -> str | None:
        value = await self._mediator.prompt(label, placeholder="optional")
        return value or None

    async def _prompt_minutes(self) -> int | None:
        while True:
            raw = await self._mediator.prompt("Minutes per day", placeholder="optional")
            if not raw:
                return None
            try:
                minutes = int(raw)
            except ValueError:
                await self._mediator.show_error("Minutes per day must be a number.")
                continue
            if minutes < 1:
                await self._mediator.show_error("Minutes per day must be at least 1.")
                continue
            return minutes


def _parse_preferences(raw: str) -> PreferenceMap:
    preferences: PreferenceMap = {}
    if not raw:
        return preferences
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            preferences[key] = value.strip() or None
    return preferences
