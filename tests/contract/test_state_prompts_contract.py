import inspect

import pytest
from pydantic import ValidationError

PROMPT_CONTRACT = [
    (
        "milai.agents.assessment",
        "build_assessment_step_instructions",
        "milai.models.assessment",
        "NextQuestion",
    ),
    (
        "milai.llm.prompts.curriculum",
        "build_generation_prompt",
        "milai.llm.prompts.curriculum",
        "CurriculumDraft",
    ),
    (
        "milai.llm.prompts.curriculum",
        "build_adjustment_prompt",
        "milai.llm.prompts.curriculum",
        "CurriculumDraft",
    ),
    (
        "milai.llm.prompts.curriculum",
        "build_extension_prompt",
        "milai.llm.prompts.curriculum",
        "CurriculumDraft",
    ),
    ("milai.llm.prompts.deviation", "build_chat_prompt", None, None),
]


@pytest.mark.parametrize(
    ("module_path", "builder_name", "response_model_module", "response_model_name"),
    PROMPT_CONTRACT,
)
def test_llm_backed_states_have_pure_builders_and_schema_models(
    module_path: str,
    builder_name: str,
    response_model_module: str | None,
    response_model_name: str | None,
) -> None:
    module = __import__(module_path, fromlist=[builder_name])
    builder = getattr(module, builder_name)

    assert inspect.isfunction(builder)
    assert not inspect.iscoroutinefunction(builder)

    if response_model_module is not None and response_model_name is not None:
        model_module = __import__(response_model_module, fromlist=[response_model_name])
        response_model = getattr(model_module, response_model_name)
        assert hasattr(response_model, "model_validate")
        with pytest.raises(ValidationError):
            response_model.model_validate({"unexpected": object()})


def test_assessment_prompt_output_uses_provider_neutral_message() -> None:
    from milai.agents.assessment import build_assessment_step_instructions
    from milai.llm.types import Message, Role

    message = build_assessment_step_instructions(
        instructions=(
            "Evaluate the latest learner answer from history. Otherwise record "
            "the evidence and ask a follow-up question."
        ),
        usable_evidence_needed=6,
        question_budget_remaining=20,
    )

    assert isinstance(message, Message)
    assert message.role is Role.USER

    rendered = message.content
    assert "{{" not in rendered
    assert "API_KEY" not in rendered
