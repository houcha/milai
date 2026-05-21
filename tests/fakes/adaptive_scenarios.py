"""Reusable fixtures for adaptive assessment, curriculum, and lesson flows."""

from typing import Literal

from milai.models.assessment import AssessmentQuestion
from milai.models.curriculum import Curriculum, Exercise, Lesson, Module
from milai.models.user_state import Skill, UserProfile, UserState
from milai.state.variants import (
    AssessmentReviewState,
    AssessmentState,
    CurriculumGenerationState,
    CurriculumReviewState,
    LessonPracticeState,
    LessonState,
)


def spanish_profile(*, fluency_level: str = "A1") -> UserProfile:
    return UserProfile(
        target_language="Spanish",
        native_language="English",
        fluency_level=fluency_level,
        learning_goal="Hold practical travel conversations.",
        preferences={"style": "Short explanations with practice."},
    )


def assessment_question(
    text: str = "Translate good morning.",
    *,
    answer: str | None = None,
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner",
) -> AssessmentQuestion:
    return AssessmentQuestion(text=text, user_answer=answer, difficulty=difficulty)


def answered_assessment_questions(count: int = 3) -> list[AssessmentQuestion]:
    return [
        assessment_question(
            f"Question {idx}",
            answer=f"answer {idx}",
        )
        for idx in range(1, count + 1)
    ]


def assessment_state_with_pending_question() -> AssessmentState:
    questions = answered_assessment_questions(2)
    questions.append(assessment_question("Pending question"))
    return AssessmentState(questions=questions, current_idx=2)


def completed_assessment_review_state() -> AssessmentReviewState:
    return AssessmentReviewState(
        fluency_level="A1",
        fluency_rationale="Can handle greetings; needs verb practice.",
        assessment_questions=answered_assessment_questions(),
    )


def curriculum_generation_state() -> CurriculumGenerationState:
    return CurriculumGenerationState(
        assessment_questions=answered_assessment_questions()
    )


def curriculum_review_state() -> CurriculumReviewState:
    return CurriculumReviewState()


def travel_curriculum() -> Curriculum:
    return Curriculum(
        modules=[
            Module(
                title="Travel Basics",
                lessons=[
                    Lesson(
                        title="Greetings",
                        theory="Hola means hello.",
                        exercises=[
                            Exercise(
                                instruction="Translate hello.",
                                exercise_type="translation",
                                skill_topics=["greetings"],
                            )
                        ],
                    )
                ],
            )
        ]
    )


def assessed_user() -> UserState:
    return UserState(
        profile=spanish_profile(),
        skills=[
            Skill(topic="greetings", strength=0.7),
            Skill(topic="present tense", strength=0.2),
        ],
    )


def user_with_curriculum() -> UserState:
    user = assessed_user()
    user.curriculum = travel_curriculum()
    return user


def lesson_state() -> LessonState:
    return LessonState()


def lesson_practice_state() -> LessonPracticeState:
    return LessonPracticeState()
