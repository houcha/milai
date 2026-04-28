import inspect

import pytest
from pydantic import ValidationError

PROMPT_CONTRACT = [
    (
        "milai.llm.prompts.assessment",
        "build_question_prompt",
        "AssessmentQuestionBatch",
    ),
    ("milai.llm.prompts.assessment", "build_fluency_prompt", "FluencyResult"),
    ("milai.llm.prompts.curriculum", "build_generation_prompt", "CurriculumDraft"),
    ("milai.llm.prompts.curriculum", "build_adjustment_prompt", "CurriculumDraft"),
    ("milai.llm.prompts.curriculum", "build_extension_prompt", "CurriculumDraft"),
    ("milai.llm.prompts.lesson", "build_lesson_prompt", "LessonContent"),
    ("milai.llm.prompts.lesson", "build_dynamic_change_prompt", "LessonContent"),
    ("milai.llm.prompts.feedback", "build_feedback_prompt", "ExerciseFeedback"),
    ("milai.llm.prompts.deviation", "build_chat_prompt", None),
]


@pytest.mark.parametrize(
    ("module_path", "builder_name", "response_model_name"), PROMPT_CONTRACT
)
def test_llm_backed_states_have_pure_builders_and_schema_models(
    module_path: str,
    builder_name: str,
    response_model_name: str | None,
) -> None:
    module = __import__(module_path, fromlist=[builder_name])
    builder = getattr(module, builder_name)

    assert inspect.isfunction(builder)
    assert not inspect.iscoroutinefunction(builder)

    if response_model_name is not None:
        response_model = getattr(module, response_model_name)
        assert hasattr(response_model, "model_validate")
        with pytest.raises(ValidationError):
            response_model.model_validate({"unexpected": object()})


def test_assessment_prompt_output_uses_provider_neutral_messages() -> None:
    from milai.llm.prompts.assessment import build_question_prompt
    from milai.llm.types import Message, Role
    from milai.models.user_state import UserProfile, UserState
    from milai.state.variants import AssessmentState

    state = AssessmentState()
    user = UserState(
        profile=UserProfile(
            target_language="Spanish",
            native_language="English",
            learning_goal="travel",
            preferences={
                "teaching_preferences": "Use plain examples and avoid grammar jargon."
            },
        )
    )

    messages = build_question_prompt(state, user)

    assert isinstance(messages, list)
    assert messages
    assert all(isinstance(message, Message) for message in messages)
    assert any(message.role is Role.SYSTEM for message in messages)
    assert any(message.role is Role.USER for message in messages)

    rendered = "\n".join(message.content for message in messages)
    assert "{{" not in rendered
    assert "API_KEY" not in rendered
