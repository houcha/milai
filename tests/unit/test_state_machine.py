import asyncio
from contextlib import contextmanager

from milai.observability import NoopObservability


def test_machine_loads_initial_snapshot_runs_handler_and_persists_transition() -> None:
    from milai.models.session import LearningSession
    from milai.models.user_state import UserState
    from milai.state.machine import StateMachine
    from milai.state.variants import AssessmentState, OnboardingState
    from tests.fakes.storage_client import InMemoryStorage

    class OnboardingHandler:
        async def step(self, session):
            assert isinstance(session.app, OnboardingState)
            return session.model_copy(update={"app": AssessmentState()})

    session = LearningSession(user=UserState(), app=OnboardingState())
    storage = InMemoryStorage(session)
    machine = StateMachine(
        storage=storage,
        handlers={OnboardingState: OnboardingHandler()},
        observability=NoopObservability(),
    )

    async def run_script() -> None:
        await machine.run(max_steps=1)

    asyncio.run(run_script())

    assert storage.save_count == 1
    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, AssessmentState)
    assert saved.id == session.id


def test_machine_saves_after_each_transition_and_stops_on_terminal_step() -> None:
    from milai.models.session import LearningSession
    from milai.models.user_state import UserState
    from milai.state.machine import HandlerMap, StateMachine
    from milai.state.variants import LessonCompleteState, LessonState
    from tests.fakes.storage_client import InMemoryStorage

    class LessonHandler:
        async def step(self, session):
            return session.model_copy(update={"app": LessonCompleteState()})

    class LessonCompleteHandler:
        async def step(self, session):
            return None

    storage = InMemoryStorage(LearningSession(user=UserState(), app=LessonState()))
    handlers: HandlerMap = {
        LessonState: LessonHandler(),
        LessonCompleteState: LessonCompleteHandler(),
    }
    machine = StateMachine(
        storage=storage,
        handlers=handlers,
        observability=NoopObservability(),
    )

    asyncio.run(machine.run(max_steps=5))

    assert storage.save_count == 1
    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, LessonCompleteState)


def test_machine_traces_each_state_dispatch_and_outputs_next_state() -> None:
    from milai.models.session import LearningSession
    from milai.models.user_state import UserState
    from milai.state.machine import HandlerMap, StateMachine
    from milai.state.variants import AssessmentState, OnboardingState
    from tests.fakes.storage_client import InMemoryStorage

    class OnboardingHandler:
        async def step(self, session):
            return session.model_copy(update={"app": AssessmentState()})

    observability = RecordingObservability()
    storage = InMemoryStorage(LearningSession(user=UserState(), app=OnboardingState()))
    handlers: HandlerMap = {OnboardingState: OnboardingHandler()}
    machine = StateMachine(
        storage=storage,
        handlers=handlers,
        observability=observability,
    )

    asyncio.run(machine.run(max_steps=1))

    assert observability.dispatches == [
        {"name": "milai.state.onboarding", "output": {"nextState": "assessment"}}
    ]


def test_machine_traces_terminal_stop() -> None:
    from milai.models.session import LearningSession
    from milai.models.user_state import UserState
    from milai.state.machine import HandlerMap, StateMachine
    from milai.state.variants import LessonCompleteState
    from tests.fakes.storage_client import InMemoryStorage

    class LessonCompleteHandler:
        async def step(self, session):
            return None

    observability = RecordingObservability()
    storage = InMemoryStorage(
        LearningSession(user=UserState(), app=LessonCompleteState())
    )
    handlers: HandlerMap = {LessonCompleteState: LessonCompleteHandler()}
    machine = StateMachine(
        storage=storage,
        handlers=handlers,
        observability=observability,
    )

    asyncio.run(machine.run(max_steps=1))

    assert observability.dispatches == [
        {"name": "milai.state.lesson_complete", "output": {"terminal": True}}
    ]


class RecordingObservation:
    def __init__(self, record):
        self._record = record

    def update(self, **kwargs):
        self._record["output"] = kwargs["output"]


class RecordingObservability:
    def __init__(self) -> None:
        self.dispatches = []

    @contextmanager
    def span(self, name, *, input=None):
        _ = input
        yield RecordingObservation({"name": name})

    @contextmanager
    def state_dispatch(self, session):
        record = {"name": f"milai.state.{session.app.type}"}
        self.dispatches.append(record)
        yield RecordingObservation(record)

    def shutdown(self) -> None:
        pass
