"""Workflow state machine and handler dispatch."""

from collections.abc import Mapping
from typing import Protocol

from milai.models.session import LearningSession
from milai.models.user_state import UserState
from milai.state.variants import (
    AppState,
    OnboardingState,
)
from milai.storage.client import StorageClient


class StateHandler(Protocol):
    async def step(self, session: LearningSession) -> LearningSession | None:
        """Run one workflow step and return the next session."""


# This is basically a tiny hand-rolled dynamic-dispatch table.
# It may look like over-engineering but it is actually an optimal trade-off between
# simplicity and maintainability/testability.
#
# The obvious OOP alternative is to put `step()` on each AppState variant and
# call `await app.step(user)`. That looks cleaner until `step()` needs real
# runtime dependencies: mediator, LLM clients, prompt builders, schedulers,
# config, etc. Then a data-focused class becomes responsible for state-specific
# behavior plus service wiring, or every `step()` takes a giant "context"
# parameter that is just this handler registry in disguise. Either way, the
# learning session model stops being a plain description of where the workflow is.
#
# The other obvious alternative is a big `match app:` in StateMachine. That
# keeps states as data, but grows a second hand-maintained list of states and
# forces the machine to know every handler attribute by name, which makes the
# dispatch code harder to maintain and noisier to test.
#
# A type-keyed handler map keeps the split explicit:
# * state = durable workflow data
# * handler = runtime behavior and dependencies,
# * machine = load -> dispatch -> save loop.
type HandlerMap = Mapping[type[AppState], StateHandler]


class StateMachine:
    def __init__(self, *, storage: StorageClient, handlers: HandlerMap) -> None:
        self._storage = storage
        self._handlers = handlers

    async def run(self, *, max_steps: int | None = None) -> None:
        """Run until a handler stops the workflow or max_steps is reached.

        max_steps is mainly for tests that need to assert one or two transitions
        without constructing the full workflow.
        """
        snapshot = await self._storage.load()
        if snapshot is None:
            snapshot = LearningSession(user=UserState(), app=OnboardingState())

        steps = 0
        while max_steps is None or steps < max_steps:
            result = await self._dispatch(snapshot)
            if result is None:
                return
            snapshot = result
            await self._storage.save(snapshot)
            steps += 1

    async def _dispatch(self, session: LearningSession) -> LearningSession | None:
        app = session.app
        handler = self._require(type(app), app)
        return await handler.step(session)

    def _require(self, state_type: type[AppState], app: AppState) -> StateHandler:
        try:
            return self._handlers[state_type]
        except KeyError:
            msg = f"no handler registered for app state {app.type!r}"
            raise RuntimeError(msg) from None
