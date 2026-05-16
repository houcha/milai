from milai.llm.prompts.curriculum import CurriculumDraft, build_generation_prompt
from milai.models.assessment import AssessmentQuestion
from milai.models.curriculum import Curriculum, Lesson, Module
from milai.models.user_state import UserProfile, UserState
from milai.state.variants import CurriculumGenerationState


def test_generation_prompt_includes_assessment_answers_for_skill_inference() -> None:
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            fluency_level="A1",
        )
    )
    state = CurriculumGenerationState(
        assessment_questions=[
            AssessmentQuestion(
                text="Translate: good morning",
                user_answer="morning answer",
                difficulty="beginner",
            )
        ]
    )

    rendered = "\n".join(
        message.content for message in build_generation_prompt(state, user)
    )

    assert "Spanish" in rendered
    assert "morning answer" in rendered
    assert "initial skill" in rendered.lower()
    assert CurriculumDraft.model_validate(
        {
            "curriculum": Curriculum(
                modules=[Module(title="Basics", lessons=[Lesson(title="Hello")])]
            ).model_dump(),
            "initial_skills": [{"topic": "greetings"}],
        }
    )
