# ruff: noqa: E501
"""Typed tools for skill-focused lessons."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from agents import (
    Agent,
    Model,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    Tool,
    function_tool,
)
from agents.exceptions import ModelBehaviorError
from openai.types.shared import Reasoning
from pydantic import BaseModel, ConfigDict, Field

from milai.exercises import GeneratedExerciseContract
from milai.pronunciation import document_fields, extract_fields
from milai.retrieval import retrieve
from milai.store import InvalidReference, Store


def tool_error(ctx, error: Exception) -> str:
    """Return correctable contract errors to the model; propagate operational faults."""
    if isinstance(error, ModelBehaviorError):
        return json.dumps(
            {
                "error": "invalid_tool_arguments",
                "saved": False,
                "guidance": "Return valid JSON matching the tool schema and correct the rejected call.",
            }
        )
    if isinstance(error, InvalidReference):
        return json.dumps(
            {
                "error": "invalid_reference",
                "saved": False,
                "guidance": "Use exact learner-owned IDs from state or successful tool results; never invent IDs.",
            }
        )
    if isinstance(error, ValueError):
        return json.dumps(
            {"error": "invalid_operation", "saved": False, "guidance": str(error)}
        )
    raise error


class LearnerFact(BaseModel):
    field: Literal[
        "target_language",
        "explanation_language",
        "level",
        "goals",
        "interests",
        "source_preferences",
        "teaching_preferences",
    ]
    value: str = Field(min_length=1, max_length=600)
    learner_quote: str = Field(min_length=1, max_length=1000)


class SkillSpec(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=800)
    success_criteria: list[str] = Field(min_length=1, max_length=5)


class LessonIntent(BaseModel):
    intent: str = Field(min_length=1, max_length=800)


class SupersessionRelation(BaseModel):
    old_skill_id: str
    new_skill_ref: str
    relation: Literal["redefined", "split", "merged"]


class SkillReplacement(BaseModel):
    old_skill_id: str
    replacement_ref: str


class SupersedeSkillsInput(BaseModel):
    old_skill_ids: list[str] = Field(min_length=1, max_length=8)
    new_skills: list[SkillSpec] = Field(min_length=1, max_length=8)
    relations: list[SupersessionRelation] = Field(min_length=1, max_length=20)
    replacements: list[SkillReplacement] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1200)


class ExerciseSkill(BaseModel):
    skill_id: str
    role: Literal["target", "supporting"]
    success_criterion: str = Field(min_length=1, max_length=500)


class ExerciseContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: GeneratedExerciseContract
    scaffolding: Literal["none", "cues", "worked_example"]


class Exercise(ExerciseContent):
    skills: list[ExerciseSkill] = Field(min_length=1, max_length=6)
    source_ids: list[str] = Field(default_factory=list, max_length=5)
    early_revisit_request: str | None = Field(default=None, max_length=800)


class SkillObservation(BaseModel):
    skill_id: str
    outcome: Literal["success", "needs_work", "uncertain"]
    issue_severity: Literal["none", "minor", "substantial", "unclear"]
    rationale: str = Field(min_length=1, max_length=1000)


class AnswerScore(BaseModel):
    correct: int = Field(
        ge=0, le=100, description="Number of required answer parts answered correctly."
    )
    total: int = Field(
        ge=1,
        le=100,
        description="All required answer parts, including missing or incorrect parts. Count only the task's explicit requirements, consistently regardless of the learner's response; one part for a single open-ended task.",
    )


class BlankResult(BaseModel):
    blank_number: int = Field(
        ge=1, le=12, description="One-based marker position in reading order."
    )
    correct: bool
    feedback: str = Field(
        max_length=600,
        description="Empty for a correct fill. For an incorrect or missing fill, give the correction and a brief explanation of that error only.",
    )


class ItemResult(BaseModel):
    item_number: int = Field(ge=1, le=12)
    correct: bool
    feedback: str = Field(
        max_length=600,
        description="Empty when correct; otherwise a correction or example and a brief explanation of the target error.",
    )


class AttemptAssessment(BaseModel):
    exercise_id: str
    feedback: str = Field(
        max_length=1600,
        description="Typed exercises: leave empty and use item_results. Legacy inline blanks: leave empty and use blank_results. Legacy free-text tasks: briefly explain the assessment. Never invite resubmission.",
    )
    score: AnswerScore | None = Field(
        default=None,
        description="Legacy exercises only. For typed exercises use null; the app calculates the score.",
    )
    item_results: list[ItemResult] = Field(
        default_factory=list,
        max_length=12,
        description="Typed exercises: exactly one result per numbered item. Leave feedback and blank_results empty. Legacy exercises: use [].",
    )
    blank_results: list[BlankResult] = Field(
        default_factory=list,
        max_length=12,
        description="Legacy tasks with {{blank}} markers only: assess every blank exactly once in order, counting one score part per blank. For all typed exercises and other legacy tasks use [].",
    )
    observations: list[SkillObservation] = Field(min_length=1, max_length=6)


@dataclass
class Context:
    store: Store
    learner: str
    session: str
    turn_id: str
    message: str
    prompt_version: str
    model: Model | None = None
    generation_model: Model | None = None
    generation_max_tokens: int = 32768
    generation_reasoning_effort: Literal[
        "none", "minimal", "low", "medium", "high", "xhigh", "max"
    ] = "low"
    generation_service_tier: str = "fast"
    planner_instructions: str = ""
    lesson_planning_calls: int = 0
    max_tools: int = 20
    calls: int = 0
    event_ids: list[str] = field(default_factory=list)
    exercise_ids: list[str] = field(default_factory=list)
    lesson_ids: list[str] = field(default_factory=list)
    lesson_id: str | None = None
    section_id: str | None = None
    selected_text: str | None = None
    origin_lesson_id: str | None = None
    action: Literal["message", "answer"] = "message"
    selected_exercise_id: str | None = None
    assessments: list[dict] = field(default_factory=list)
    on_progress: Callable[[dict], Awaitable[None]] | None = None

    def check(self) -> None:
        self.store.authorize(self.learner, self.session)
        self.calls += 1
        if self.calls > self.max_tools:
            raise RuntimeError("Tool budget exhausted")


@function_tool(failure_error_function=tool_error)
async def record_learner_facts(
    ctx: RunContextWrapper[Context], facts: list[LearnerFact]
) -> dict:
    """Save explicit learner facts in a batch, each backed by an exact quote from this message."""
    c = ctx.context
    c.check()
    if not 1 <= len(facts) <= 6:
        raise ValueError("Save 1–6 facts at a time")
    for fact in facts:
        if fact.learner_quote not in c.message:
            raise ValueError(
                "Every learner_quote must be an exact substring of the current message"
            )
    saved = c.store.record_facts(c, [fact.model_dump() for fact in facts])
    return {"saved": True, "facts": saved}


@function_tool(failure_error_function=tool_error)
async def search_skills(
    ctx: RunContextWrapper[Context], language: str, query: str = "", limit: int = 20
) -> dict:
    """Find reusable active skills in the learner's language-specific skill catalog."""
    c = ctx.context
    c.check()
    if not 1 <= limit <= 30 or len(query) > 200 or len(language) > 100:
        raise ValueError("Search bounds exceeded")
    return {"skills": c.store.search_skills(c.learner, language, query, limit)}


class LessonSection(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=80, max_length=16000)


class WorkedExample(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=40, max_length=8000)


class LessonDocument(BaseModel):
    objective: str = Field(min_length=20, max_length=800)
    sections: list[LessonSection] = Field(min_length=2, max_length=8)
    worked_examples: list[WorkedExample] = Field(min_length=2, max_length=8)
    recap: str = Field(min_length=40, max_length=4000)


class PlannedExerciseSkill(BaseModel):
    skill_key: str = Field(min_length=1, max_length=120)
    role: Literal["target", "supporting"]
    success_criterion: str = Field(min_length=1, max_length=500)


class PlannedExercise(ExerciseContent):
    skills: list[PlannedExerciseSkill] = Field(min_length=1, max_length=6)
    source_ids: list[str] = Field(max_length=5)


class _LessonPlan(BaseModel):
    """Complete read-only draft selected by the private lesson planner."""

    existing_skill_key: str | None
    new_skill: SkillSpec | None
    prerequisite_keys: list[str] = Field(max_length=8)
    reason: str = Field(min_length=1, max_length=800)
    document: LessonDocument
    exercises: list[PlannedExercise] = Field(min_length=3, max_length=6)


def _validated_lesson_draft(
    plan: _LessonPlan, keyed: dict[str, dict], source_ids: set[str]
) -> tuple[dict, list[dict]]:
    """Resolve planner keys and reject an incomplete document before any write."""
    if (plan.existing_skill_key is None) == (plan.new_skill is None):
        raise RuntimeError("Planner must select exactly one existing or new skill")
    if plan.existing_skill_key is not None:
        if plan.existing_skill_key not in keyed:
            raise RuntimeError("Planner referenced an unknown focus skill")
        if plan.prerequisite_keys:
            raise RuntimeError("Existing skill prerequisites cannot be changed")
        focus_key = plan.existing_skill_key
        focus_skill = keyed[focus_key]
        focus_id = focus_skill["id"]
    else:
        if plan.new_skill is None:
            raise RuntimeError("Planner omitted the new skill")
        focus_key = plan.new_skill.key
        if focus_key in keyed:
            raise RuntimeError("Planner recreated an existing skill key")
        if any(len(item) > 500 for item in plan.new_skill.success_criteria):
            raise RuntimeError("Planner skill criteria exceed content bounds")
        focus_skill = plan.new_skill.model_dump()
        focus_id = "@focus"
    if len(set(plan.prerequisite_keys)) != len(plan.prerequisite_keys):
        raise RuntimeError("Planner repeated a prerequisite")
    if any(key not in keyed for key in plan.prerequisite_keys):
        raise RuntimeError("Planner referenced an unknown prerequisite")
    if focus_key in plan.prerequisite_keys:
        raise RuntimeError("A lesson skill cannot be its own prerequisite")

    document = plan.document.model_dump()
    extract_fields(document, document_fields(document))
    section_ids = [item.id for item in plan.document.sections]
    example_ids = [item.id for item in plan.document.worked_examples]
    if len(set(section_ids + example_ids)) != len(section_ids + example_ids):
        raise RuntimeError("Lesson section and example IDs must be unique")
    document_text_length = len(plan.document.objective) + len(plan.document.recap)
    document_text_length += sum(
        len(item.title) + len(item.markdown) for item in plan.document.sections
    )
    document_text_length += sum(
        len(item.title) + len(item.markdown) for item in plan.document.worked_examples
    )
    if document_text_length > 32000:
        raise RuntimeError("Lesson document exceeds 32,000 characters")

    if sum(item.scaffolding == "none" for item in plan.exercises) < 2:
        raise RuntimeError("Lesson needs at least two unscaffolded exercises")
    resolved_exercises: list[dict] = []
    for exercise in plan.exercises:
        keys = [item.skill_key for item in exercise.skills]
        targets = [item.skill_key for item in exercise.skills if item.role == "target"]
        if len(keys) != len(set(keys)) or targets != [focus_key]:
            raise RuntimeError(
                "Each exercise needs the selected focus as its sole target"
            )
        if len(exercise.source_ids) != len(set(exercise.source_ids)) or any(
            source_id not in source_ids for source_id in exercise.source_ids
        ):
            raise RuntimeError("Exercise referenced an unavailable source excerpt")
        skills = []
        for item in exercise.skills:
            skill = (
                focus_skill
                if item.skill_key == focus_key
                else keyed.get(item.skill_key)
            )
            if skill is None:
                raise RuntimeError("Exercise referenced an unknown skill key")
            if item.success_criterion not in skill["success_criteria"]:
                raise RuntimeError(
                    "Exercise criterion does not match the skill catalog"
                )
            skills.append(
                {
                    "skill_id": focus_id
                    if item.skill_key == focus_key
                    else skill["id"],
                    "role": item.role,
                    "success_criterion": item.success_criterion,
                }
            )
        resolved_exercises.append(
            {
                "contract": exercise.contract.model_dump(),
                "scaffolding": exercise.scaffolding,
                "skills": skills,
                "source_ids": exercise.source_ids,
                "early_revisit_request": None,
            }
        )
    return document, resolved_exercises


@function_tool(failure_error_function=tool_error)
async def start_lesson(ctx: RunContextWrapper[Context], lesson: LessonIntent) -> dict:
    """Plan and start one language-skill lesson, informed by learner goals and skill evidence."""
    c = ctx.context
    c.check()
    profile = c.store.profile(c.learner)
    language_fact = profile.get("target_language")
    if language_fact is None:
        raise ValueError("Record the target language before starting a lesson")
    if c.generation_model is None or not c.planner_instructions:
        raise RuntimeError("Lesson planner is unavailable")
    if c.store.db.execute(
        "SELECT 1 FROM events WHERE learner=? AND turn_id=? AND kind='lesson' LIMIT 1",
        (c.learner, c.turn_id),
    ).fetchone():
        raise ValueError("A lesson was already started in this learner turn")
    c.lesson_planning_calls += 1
    if c.lesson_planning_calls > 1:
        raise RuntimeError("Only one lesson generation is allowed per learner turn")
    language = language_fact["value"]
    candidates = c.store.search_skills(c.learner, language, "", 30)
    keyed = {skill["key"]: skill for skill in candidates}
    source_rows = c.store.db.execute(
        "SELECT id FROM sources WHERE learner=? AND status='available' "
        "ORDER BY rowid DESC LIMIT 4",
        (c.learner,),
    ).fetchall()
    source_excerpts = [
        c.store.source_excerpt(c.learner, row["id"], 0, 2000) for row in source_rows
    ]
    planner = Agent(
        name="Language lesson planner",
        instructions=c.planner_instructions,
        model=c.generation_model,
        output_type=_LessonPlan,
        model_settings=ModelSettings(
            max_tokens=c.generation_max_tokens,
            reasoning=Reasoning(effort=c.generation_reasoning_effort),
            extra_body={"service_tier": c.generation_service_tier},
            store=False,
            response_include=["reasoning.encrypted_content"],
        ),
    )
    planner_input = "Choose one lesson from this application data:\n" + json.dumps(
        {
            "target_language": language,
            "learner_profile": {
                field: fact["value"] for field, fact in profile.items()
            },
            "learner_message": c.message,
            "lesson_intent": lesson.intent,
            "active_lesson": c.store.active_lesson(c.learner),
            "review_due": c.store.review_due(c.learner),
            "reusable_active_skills": [
                {
                    **skill,
                    "mastered": c.store.mastered(c.learner, skill["id"]),
                    "prerequisite_keys": [
                        next(
                            (
                                other["key"]
                                for other in candidates
                                if other["id"] == item
                            ),
                            item,
                        )
                        for item in c.store.prerequisites(c.learner, skill["id"])
                    ],
                }
                for skill in candidates
            ],
            "skill_evidence": c.store.progress(
                c.learner, [skill["id"] for skill in candidates]
            ),
            "validated_source_excerpts": source_excerpts,
        },
        ensure_ascii=False,
    )
    if c.on_progress is not None:
        await c.on_progress({"type": "stage", "text": "Generating your lesson…"})
    try:
        planned = await Runner.run(
            planner,
            planner_input,
            max_turns=1,
            run_config=RunConfig(trace_include_sensitive_data=True),
        )
    except ModelBehaviorError as exc:
        raise RuntimeError("Lesson planner returned invalid structured output") from exc
    plan = planned.final_output
    if not isinstance(plan, _LessonPlan):
        raise RuntimeError("Lesson planner returned an unexpected result")
    if c.on_progress is not None:
        await c.on_progress({"type": "stage", "text": "Checking lesson and practice…"})
    document, exercises = _validated_lesson_draft(
        plan, keyed, {item["source_id"] for item in source_excerpts}
    )
    active = c.store.active_lesson(c.learner)
    if (
        active
        and plan.existing_skill_key
        and keyed[plan.existing_skill_key]["id"] == active["focus_skill_id"]
    ):
        raise ValueError(
            "The selected skill already has the active lesson. No new lesson was saved. "
            "For explicitly requested extra practice, use present_exercise in that "
            "existing lesson. Do not substitute extra practice for a request to move "
            "forward, and do not retry start_lesson in this turn."
        )
    if c.on_progress is not None:
        await c.on_progress({"type": "stage", "text": "Saving lesson…"})
    with c.store.savepoint():
        try:
            saved = c.store.start_lesson(
                c,
                language,
                keyed[plan.existing_skill_key]["id"]
                if plan.existing_skill_key
                else None,
                plan.new_skill.model_dump() if plan.new_skill else None,
                [keyed[key]["id"] for key in plan.prerequisite_keys],
                plan.reason,
                document=document,
                exercises=exercises,
            )
        except ValueError as exc:
            raise RuntimeError(
                "Generated lesson failed application validation"
            ) from exc
    c.lesson_ids.append(saved["id"])
    return saved


@function_tool(failure_error_function=tool_error)
async def supersede_skills(
    ctx: RunContextWrapper[Context], change: SupersedeSkillsInput
) -> dict:
    """Version, split, or merge skills while preserving old observations as historical evidence."""
    c = ctx.context
    c.check()
    for skill in change.new_skills:
        if any(len(criterion) > 500 for criterion in skill.success_criteria):
            raise ValueError(
                "Skill success criteria must each be at most 500 characters"
            )
    with c.store.savepoint():
        return c.store.supersede_skills(
            c,
            change.old_skill_ids,
            [item.model_dump() for item in change.new_skills],
            [item.model_dump() for item in change.relations],
            [item.model_dump() for item in change.replacements],
            change.reason,
        )


@function_tool(failure_error_function=tool_error)
async def present_exercise(ctx: RunContextWrapper[Context], exercise: Exercise) -> dict:
    """Persist and queue a lesson-focused exercise card; the application renders it exactly."""
    c = ctx.context
    c.check()
    if c.action == "answer":
        raise ValueError(
            "Assess this answer without generating more exercises. Fresh practice is available on a later learner request."
        )
    return c.store.present_exercise(c, exercise.model_dump())


@function_tool(failure_error_function=tool_error)
async def record_assistance(
    ctx: RunContextWrapper[Context],
    exercise_id: str,
    skill_ids: list[str],
    level: Literal["explanation", "answer_shown"],
    content: str,
) -> dict:
    """Record help against the exact exercise skills it assisted before giving that help."""
    c = ctx.context
    c.check()
    if c.selected_exercise_id and c.selected_exercise_id != exercise_id:
        raise ValueError("Assistance must match the selected exercise")
    if not 1 <= len(content) <= 2400 or not 1 <= len(skill_ids) <= 6:
        raise ValueError("Assistance content or skill count exceeds bounds")
    return c.store.record_assistance(c, exercise_id, skill_ids, level, content)


@function_tool(failure_error_function=tool_error)
async def assess_attempt(
    ctx: RunContextWrapper[Context], assessment: AttemptAssessment
) -> dict:
    """Save an explicit submission's assessment and learning evidence."""
    c = ctx.context
    c.check()
    return persist_assessment(c, assessment)


def persist_assessment(c: Context, assessment: AttemptAssessment) -> dict:
    """Validate and persist an assessment from a tool or the private reviewer."""
    if c.action != "answer":
        raise ValueError("Assess only an explicit exercise answer submission")
    if c.selected_exercise_id and c.selected_exercise_id != assessment.exercise_id:
        raise ValueError("Assessment must match the selected exercise answer")
    if assessment.score is None and not c.store.exercise_contract(
        c.learner, assessment.exercise_id
    ):
        raise ValueError(
            "Legacy assessments require a score of the requested answer parts"
        )
    result = c.store.assess_attempt(
        c,
        assessment.exercise_id,
        assessment.feedback,
        [item.model_dump() for item in assessment.observations],
        score=assessment.score.model_dump() if assessment.score else None,
        blank_results=[item.model_dump() for item in assessment.blank_results],
        item_results=[item.model_dump() for item in assessment.item_results],
    )
    c.assessments.append(result)
    practice = c.store.exercise_practice_result(c.learner, assessment.exercise_id)
    result["practice_result"] = practice
    if practice["finished"]:
        result["practice_assessments"] = [
            {
                "exercise_id": exercise_id,
                "assessment": {
                    key: result[key]
                    for key in (
                        "learner_response",
                        "feedback",
                        "score",
                        "blank_results",
                        "item_results",
                        "observations",
                    )
                }
                if exercise_id == assessment.exercise_id
                else c.store.exercise_status(c.learner, c.session, exercise_id)[
                    "first_assessment"
                ],
            }
            for exercise_id in practice["exercise_ids"]
        ]
    return result


@function_tool(failure_error_function=tool_error)
async def recall_learning_context(ctx: RunContextWrapper[Context]) -> dict:
    """Recall bounded profile, lesson, exercise, and evidence summaries."""
    c = ctx.context
    c.check()
    return c.store.prompt_state(c.learner)


@function_tool(failure_error_function=tool_error)
async def recall_lesson_context(
    ctx: RunContextWrapper[Context],
    lesson_id: str,
    include: Literal["content", "discussion"] = "content",
    start: int = 0,
    length: int = 4000,
) -> dict:
    """Recall bounded content or discussion from one lesson owned by this session."""
    c = ctx.context
    c.check()
    if start < 0 or not 1 <= length <= 4000:
        raise ValueError("Lesson excerpt start or length is outside bounds")
    if include == "content":
        return c.store.lesson_excerpt(c.learner, lesson_id, start, length)
    if start != 0:
        raise ValueError("Discussion retrieval does not use content offsets")
    return c.store.discussion_excerpt(c.learner, lesson_id)


@function_tool(failure_error_function=tool_error)
async def retrieve_source(ctx: RunContextWrapper[Context], url: str) -> dict:
    """Retrieve learner-provided public HTTPS text/HTML and preserve attribution."""
    c = ctx.context
    c.check()
    provided_urls = {
        match.rstrip(".,!?)") for match in re.findall(r"https://[^\s<>\"']+", c.message)
    }
    if url not in provided_urls and url not in c.store.source_urls(c.learner):
        return {"status": "unavailable", "reason": "Ask the learner for this URL first"}
    try:
        source = await retrieve(url)
    except TimeoutError:
        source = {"url": url, "status": "unavailable", "reason": "Retrieval timed out"}
    return c.store.save_source(c, source)


@function_tool(failure_error_function=tool_error)
async def save_pasted_source(
    ctx: RunContextWrapper[Context], label: str, text: str
) -> dict:
    """Preserve a learner-pasted excerpt as unverified source material."""
    c = ctx.context
    c.check()
    if not text or len(text) > 6000 or not label or len(label) > 300:
        raise ValueError("Pasted source exceeds limits or is empty")
    if text not in c.message:
        raise ValueError(
            "Pasted source text must be an exact substring of the current message"
        )
    return c.store.save_source(
        c,
        {
            "status": "available",
            "title": label,
            "text": text,
            "provenance": "learner_pasted_unverified",
            "url": None,
        },
    )


@function_tool(failure_error_function=tool_error)
async def get_source_excerpt(
    ctx: RunContextWrapper[Context], source_id: str, start: int = 0, length: int = 2000
) -> dict:
    """Read a bounded excerpt of one learner-owned source without loading it into persistent context."""
    c = ctx.context
    c.check()
    if start < 0 or not 1 <= length <= 4000:
        raise ValueError("Excerpt start or length is outside bounds")
    return c.store.source_excerpt(c.learner, source_id, start, length)


TOOLS: list[Tool] = [
    record_learner_facts,
    search_skills,
    start_lesson,
    supersede_skills,
    present_exercise,
    record_assistance,
    assess_attempt,
    recall_learning_context,
    recall_lesson_context,
    retrieve_source,
    save_pasted_source,
    get_source_excerpt,
]
