import asyncio


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
        storage=storage, handlers={OnboardingState: OnboardingHandler()}
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
    machine = StateMachine(storage=storage, handlers=handlers)

    asyncio.run(machine.run(max_steps=5))

    assert storage.save_count == 1
    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, LessonCompleteState)
