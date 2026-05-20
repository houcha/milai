"""Lesson-specific LLM service."""

from pydantic import BaseModel, Field

from milai.llm.client import LLMClient
from milai.llm.types import Message, Role
from milai.models.curriculum import Exercise, ExerciseEvaluation, Lesson
from milai.models.user_state import UserState
from milai.srs.scheduler import top_review_skills
from milai.state.variants import LessonState

LESSON_LLM_TIMEOUT_SECONDS = 60


class _ExerciseBatch(BaseModel):
    exercises: list[Exercise] = Field(min_length=1, max_length=5)


class LessonLLM:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def generate_lesson_content(
        self, state: LessonState, user: UserState
    ) -> Lesson:
        _ = state
        module, lesson, _module_index, _lesson_index = _active_lesson_details(user)
        theory = await self._llm.complete(
            [
                Message(
                    role=Role.USER,
                    content=(
                        f"Write the theory for lesson {lesson.title} in module "
                        f"{module.title}. Use this learner profile to choose the "
                        "level, language, examples, and teaching style: "
                        f"{user.profile.model_dump()}. Keep the output scoped to "
                        "theory only; do not include exercises."
                    ),
                ),
            ],
            timeout=LESSON_LLM_TIMEOUT_SECONDS,
        )
        return _lesson_with_theory(lesson, theory)

    async def generate_exercises(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str = "",
    ) -> list[Exercise]:
        _ = state
        module, lesson, _module_index, _lesson_index = _active_lesson_details(user)
        review_topics = [skill.topic for skill in top_review_skills(user.skills)]
        known_skills = [
            {"topic": skill.topic, "strength": skill.strength} for skill in user.skills
        ]
        requested_change_instruction = (
            f" Apply this requested change: {requested_change}."
            if requested_change
            else ""
        )
        batch = await self._llm.complete(
            [
                Message(
                    role=Role.USER,
                    content=(
                        f"Generate 2-5 exercises for lesson {lesson.title} in module "
                        f"{module.title}. Use the lesson theory as the source of "
                        f"what to practice: {lesson.theory}. Use this learner "
                        "profile and preferences to tune difficulty and tone: "
                        f"{user.profile.model_dump()}; preferences: "
                        f"{user.profile.preferences}. Use these known skills to "
                        f"avoid overtraining mastered areas: {known_skills}. Use "
                        "these review topics only as natural reinforcement, not as "
                        f"a replacement for the lesson focus: {review_topics}."
                        f"{requested_change_instruction} Return exercises with "
                        "instruction, exercise_type, and non-empty skill_topics. "
                        "Use options only for multiple_choice exercises. Do not "
                        "include answers, theory, feedback, or summaries."
                    ),
                ),
            ],
            response_model=_ExerciseBatch,
            timeout=LESSON_LLM_TIMEOUT_SECONDS,
        )
        return batch.exercises

    async def change_lesson(
        self,
        state: LessonState,
        user: UserState,
        *,
        requested_change: str,
    ) -> Lesson:
        _ = state
        module, lesson, _module_index, _lesson_index = _active_lesson_details(user)
        theory = await self._llm.complete(
            [
                Message(
                    role=Role.USER,
                    content=(
                        f"Revise only the theory for lesson {lesson.title} in "
                        f"module {module.title}. Use the current lesson content as "
                        f"the baseline: {lesson.model_dump()}. Use this learner "
                        "profile to keep the revised explanation appropriate: "
                        f"{user.profile.model_dump()}. Apply this requested change "
                        f"to theory content only: {requested_change}. Return "
                        "non-empty theory only. Do not change the title, exercises, "
                        "or outside progress."
                    ),
                ),
            ],
            timeout=LESSON_LLM_TIMEOUT_SECONDS,
        )
        changed_user = user.model_copy(deep=True)
        changed = _lesson_with_theory(
            _active_lesson(changed_user),
            theory,
            reset_progress=True,
        )
        _replace_active_lesson(changed_user, changed)
        changed.exercises = await self.generate_exercises(
            state,
            changed_user,
            requested_change=requested_change,
        )
        return changed

    async def evaluate_answer(
        self,
        exercise: Exercise,
        user: UserState,
        *,
        answer: str,
        lesson_context: str,
    ) -> ExerciseEvaluation:
        return await self._llm.complete(
            [
                Message(
                    role=Role.USER,
                    content=(
                        "Evaluate the learner's answer for the given exercise in "
                        f"this lesson context: {lesson_context}. Use this learner "
                        "profile for tone and level: "
                        f"{user.profile.model_dump()}. Use the exercise details to "
                        f"judge the answer: {exercise.model_dump()}. Use these "
                        "expected skill topics to decide which SRS topics to "
                        f"include: {exercise.skill_topics}. The learner answered: "
                        f"{answer}. Return specific feedback, correctness when "
                        "objective, and skill topics for update."
                    ),
                ),
            ],
            response_model=ExerciseEvaluation,
            timeout=LESSON_LLM_TIMEOUT_SECONDS,
        )


def _active_lesson(user: UserState) -> Lesson:
    if user.curriculum is None:
        raise ValueError("user has no curriculum")
    module = user.curriculum.modules[user.curriculum.current_module_idx]
    return module.lessons[module.current_lesson_idx]


def _replace_active_lesson(user: UserState, lesson: Lesson) -> None:
    if user.curriculum is None:
        raise ValueError("user has no curriculum")
    module = user.curriculum.modules[user.curriculum.current_module_idx]
    module.lessons[module.current_lesson_idx] = lesson


def _lesson_with_theory(
    current: Lesson,
    theory: str,
    *,
    reset_progress: bool = False,
) -> Lesson:
    lesson = current.model_copy(deep=True)
    lesson.theory = theory
    if reset_progress:
        lesson.current_exercise_idx = 0
        lesson.exercises = []
    return lesson


def _active_lesson_details(user: UserState):
    if user.curriculum is None:
        raise ValueError("user has no curriculum")
    module_index = user.curriculum.current_module_idx
    module = user.curriculum.modules[module_index]
    lesson_index = module.current_lesson_idx
    lesson = module.lessons[lesson_index]
    return module, lesson, module_index, lesson_index
