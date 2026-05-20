import asyncio


def test_machine_loads_initial_snapshot_runs_handler_and_persists_transition() -> None:
    from milai.models.state import PersistedState
    from milai.models.user_state import UserState
    from milai.state.machine import StateMachine
    from milai.state.variants import AssessmentState, OnboardingState
    from tests.fakes.storage_client import InMemoryStorage

    class OnboardingHandler:
        async def step(self, app, user):
            assert isinstance(app, OnboardingState)
            return AssessmentState(), user

    storage = InMemoryStorage(PersistedState(user=UserState(), app=OnboardingState()))
    machine = StateMachine(
        storage=storage, handlers={OnboardingState: OnboardingHandler()}
    )

    async def run_script() -> None:
        await machine.run(max_steps=1)

    asyncio.run(run_script())

    assert storage.save_count == 1
    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, AssessmentState)


def test_machine_saves_after_each_transition_and_stops_on_terminal_step() -> None:
    from milai.models.state import PersistedState
    from milai.models.user_state import UserState
    from milai.state.machine import HandlerMap, StateMachine
    from milai.state.variants import LessonCompleteState, LessonState
    from tests.fakes.storage_client import InMemoryStorage

    class LessonHandler:
        async def step(self, app, user):
            return LessonCompleteState(), user

    class LessonCompleteHandler:
        async def step(self, app, user):
            return None

    storage = InMemoryStorage(PersistedState(user=UserState(), app=LessonState()))
    handlers: HandlerMap = {
        LessonState: LessonHandler(),
        LessonCompleteState: LessonCompleteHandler(),
    }
    machine = StateMachine(storage=storage, handlers=handlers)

    asyncio.run(machine.run(max_steps=5))

    assert storage.save_count == 1
    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, LessonCompleteState)
