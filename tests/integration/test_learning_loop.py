import asyncio

from milai.llm.lesson_service import LessonLLM
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.state import PersistedState
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.curriculum_complete import CurriculumCompleteHandler
from milai.state.handlers.deviation import DeviationHandler
from milai.state.handlers.lesson import LessonHandler
from milai.state.handlers.lesson_complete import LessonCompleteHandler
from milai.state.handlers.lesson_practice import LessonPracticeHandler
from milai.state.machine import StateMachine
from milai.state.variants import (
    CurriculumCompleteState,
    DeviationState,
    LessonCompleteState,
    LessonPracticeState,
    LessonState,
)


def test_learning_loop_persists_progress_deviation_srs_and_completion() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator
    from tests.fakes.storage_client import InMemoryStorage

    mediator = ScriptedMediator(
        [
            "practice",
            "hola",
            "deviation",
            "Why plural?",
            "return",
            "practice",
            "un cafe",
        ]
    )
    llm = ScriptedLLMClient(
        [
            "Hola means hello.",
            {
                "exercises": [
                    {
                        "instruction": "Translate hello",
                        "exercise_type": "translation",
                        "skill_topics": ["greetings"],
                    }
                ]
            },
            {"feedback": "Correct.", "is_correct": True},
            "Use quiero for I want.",
            "Because some greetings are idiomatic.",
            {
                "exercises": [
                    {
                        "instruction": "Ask for a coffee",
                        "exercise_type": "open",
                        "skill_topics": ["ordering"],
                    }
                ]
            },
            {"feedback": "Good effort.", "is_correct": True},
        ]
    )
    storage = InMemoryStorage(
        PersistedState(
            user=UserState(
                profile=UserProfile(target_language="Spanish", fluency_level="A1"),
                skills=[Skill(topic="greetings", strength=0.1)],
                curriculum=Curriculum(
                    modules=[
                        Module(
                            title="Basics",
                            lessons=[
                                Lesson(title="Greetings"),
                                Lesson(title="Ordering"),
                            ],
                        )
                    ]
                ),
            ),
            app=LessonState(),
        )
    )
    machine = StateMachine(
        storage=storage,
        handlers={
            LessonState: LessonHandler(mediator, LessonLLM(llm)),
            LessonPracticeState: LessonPracticeHandler(mediator, LessonLLM(llm)),
            DeviationState: DeviationHandler(mediator, llm),
            LessonCompleteState: LessonCompleteHandler(mediator),
            CurriculumCompleteState: CurriculumCompleteHandler(mediator, llm),
        },
    )

    asyncio.run(machine.run(max_steps=11))

    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, CurriculumCompleteState)
    assert saved.user.curriculum is not None
    first, second = saved.user.curriculum.modules[0].lessons
    assert first.current_exercise_idx == 1
    assert first.exercises[0].feedback == "Correct."
    assert second.current_exercise_idx == 1
    assert second.exercises[0].user_answer == "un cafe"
    assert [skill.topic for skill in saved.user.skills] == ["greetings", "ordering"]
    assert saved.user.skills[0].strength == 0.2
    assert saved.user.skills[1].strength == 0.1
