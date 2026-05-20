import asyncio

from milai.llm.prompts.curriculum import CurriculumDraft
from milai.models.assessment import AssessmentQuestion
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.state import PersistedState
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.handlers.curriculum_gen import CurriculumGenerationHandler
from milai.state.handlers.curriculum_review import CurriculumReviewHandler
from milai.state.machine import StateMachine
from milai.state.variants import (
    CurriculumGenerationState,
    CurriculumReviewState,
    LessonState,
)


def test_curriculum_generation_review_edits_and_confirmation_persist() -> None:
    from tests.fakes.llm_client import ScriptedLLMClient
    from tests.fakes.mediator import ScriptedMediator
    from tests.fakes.storage_client import InMemoryStorage

    mediator = ScriptedMediator(
        ["feedback", "Move Travel first and remove Basics.", "confirm"]
    )
    llm = ScriptedLLMClient(
        [
            CurriculumDraft(
                curriculum=Curriculum(
                    modules=[
                        Module(title="Basics", lessons=[Lesson(title="Greetings")]),
                        Module(title="Travel", lessons=[Lesson(title="Tickets")]),
                        Module(title="Food", lessons=[Lesson(title="Ordering")]),
                    ]
                ),
                initial_skills=[
                    Skill(topic="greetings", strength=0.25),
                    Skill(topic="travel phrases", strength=0.2),
                ],
            ),
            CurriculumDraft(
                curriculum=Curriculum(
                    modules=[
                        Module(title="Travel", lessons=[Lesson(title="Tickets")]),
                        Module(title="Food", lessons=[Lesson(title="Ordering")]),
                    ]
                )
            ),
        ]
    )
    storage = InMemoryStorage(
        PersistedState(
            user=UserState(
                profile=UserProfile(
                    target_language="Spanish",
                    learning_goal="travel",
                    fluency_level="A1",
                )
            ),
            app=CurriculumGenerationState(
                assessment_questions=[
                    AssessmentQuestion(
                        text="Ask for a train ticket",
                        user_answer="ticket answer",
                    )
                ]
            ),
        )
    )
    machine = StateMachine(
        storage=storage,
        handlers={
            CurriculumGenerationState: CurriculumGenerationHandler(mediator, llm),
            CurriculumReviewState: CurriculumReviewHandler(mediator, llm),
        },
    )

    asyncio.run(machine.run(max_steps=3))

    saved = asyncio.run(storage.load())
    assert saved is not None
    assert isinstance(saved.app, LessonState)
    assert saved.user.curriculum is not None
    assert [module.title for module in saved.user.curriculum.modules] == [
        "Travel",
        "Food",
    ]
    assert [skill.topic for skill in saved.user.skills] == [
        "greetings",
        "travel phrases",
    ]
    rendered = "\n".join(message.content for message in llm.calls[0])
    assert "ticket answer" in rendered
