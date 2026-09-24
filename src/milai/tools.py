# ruff: noqa: E501
"""Typed tools for a topic-independent learner skill graph."""

from __future__ import annotations

import json
import re
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
from pydantic import BaseModel, Field

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
    ]
    value: str = Field(min_length=1, max_length=600)
    learner_quote: str = Field(min_length=1, max_length=1000)


class SkillSpec(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=800)
    success_criteria: list[str] = Field(min_length=1, max_length=5)


class TopicSpec(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=800)


class Prerequisite(BaseModel):
    prerequisite: str = Field(min_length=1, max_length=120)
    dependent: str = Field(min_length=1, max_length=120)


class TopicSkill(BaseModel):
    skill_ref: str = Field(min_length=1, max_length=120)
    role: Literal["core", "extension", "contextual"]
    priority: int = Field(ge=1, le=100)


class FocusSpec(BaseModel):
    target_refs: list[str] = Field(min_length=1, max_length=3)
    supporting_refs: list[str] = Field(default_factory=list, max_length=5)
    reason: str = Field(min_length=1, max_length=800)


class ExpandTopicInput(BaseModel):
    topic_id: str
    existing_skill_ids: list[str] = Field(default_factory=list, max_length=8)
    new_skills: list[SkillSpec] = Field(default_factory=list, max_length=8)
    prerequisites: list[Prerequisite] = Field(default_factory=list, max_length=20)
    links: list[TopicSkill] = Field(min_length=1, max_length=12)
    rationale: str = Field(min_length=1, max_length=1200)


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


class FocusInput(BaseModel):
    topic_id: str
    target_skill_ids: list[str] = Field(min_length=1, max_length=3)
    supporting_skill_ids: list[str] = Field(default_factory=list, max_length=5)
    reason: str = Field(min_length=1, max_length=800)


class ExerciseSkill(BaseModel):
    skill_id: str
    role: Literal["target", "supporting"]
    success_criterion: str = Field(min_length=1, max_length=500)


class Exercise(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=1, max_length=2400)
    context: str = Field(min_length=1, max_length=800)
    scaffolding: Literal["none", "cues", "worked_example"]
    skills: list[ExerciseSkill] = Field(min_length=1, max_length=6)
    source_ids: list[str] = Field(default_factory=list, max_length=5)


class SkillObservation(BaseModel):
    skill_id: str
    outcome: Literal["success", "needs_work", "uncertain"]
    rationale: str = Field(min_length=1, max_length=1000)


class AttemptAssessment(BaseModel):
    exercise_id: str
    feedback: str = Field(min_length=1, max_length=1600)
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
    planner_instructions: str = ""
    trace_content: bool = False
    topic_planning_calls: int = 0
    max_tools: int = 20
    calls: int = 0
    event_ids: list[str] = field(default_factory=list)
    exercise_ids: list[str] = field(default_factory=list)
    selected_exercise_id: str | None = None
    assessments: list[dict] = field(default_factory=list)

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


class _TopicPlan(BaseModel):
    """Structured output produced only by the private topic planner."""

    existing_skill_keys: list[str] = Field(default_factory=list, max_length=8)
    new_skills: list[SkillSpec] = Field(default_factory=list, max_length=8)
    prerequisites: list[Prerequisite] = Field(default_factory=list, max_length=20)
    links: list[TopicSkill] = Field(min_length=3, max_length=12)
    initial_focus: FocusSpec


def _existing_skill_ids(keys: list[str], candidates: list[dict]) -> list[str]:
    """Resolve planner-visible stable keys to learner-owned database IDs."""
    known = {skill["key"]: skill["id"] for skill in candidates}
    return [known.get(key, key) for key in keys]


@function_tool(failure_error_function=tool_error)
async def establish_topic(ctx: RunContextWrapper[Context], topic: TopicSpec) -> dict:
    """Plan and atomically establish a topic's minimum skill graph and initial focus."""
    c = ctx.context
    c.check()
    profile = c.store.profile(c.learner)
    language_fact = profile.get("target_language")
    if language_fact is None:
        raise ValueError("Record the target language before establishing a topic")
    if c.model is None or not c.planner_instructions:
        raise RuntimeError("Topic planner is unavailable")
    c.topic_planning_calls += 1
    if c.topic_planning_calls > 1:
        raise ValueError(
            "Topic establishment can be planned only once per learner turn"
        )
    target_language = language_fact["value"]
    candidates = c.store.search_skills(c.learner, target_language, "", 30)
    candidate_keys = {skill["id"]: skill["key"] for skill in candidates}
    evidence = [
        {
            "skill_key": candidate_keys[summary["id"]],
            **{key: value for key, value in summary.items() if key != "id"},
        }
        for summary in c.store.progress(c.learner, list(candidate_keys))
    ]
    planner = Agent(
        name="Topic skill-graph planner",
        instructions=c.planner_instructions,
        model=c.model,
        output_type=_TopicPlan,
        model_settings=ModelSettings(
            max_tokens=8192, reasoning=Reasoning(effort="high")
        ),
    )
    planned = await Runner.run(
        planner,
        "Plan this topic from the supplied application data:\n"
        + json.dumps(
            {
                "target_language": target_language,
                "learner_profile": {
                    field: fact["value"] for field, fact in profile.items()
                },
                "skill_evidence": evidence,
                "topic": topic.model_dump(),
                "reusable_active_skills": [
                    {
                        field: skill[field]
                        for field in ("key", "name", "definition", "success_criteria")
                    }
                    for skill in candidates
                ],
            },
            ensure_ascii=False,
        ),
        max_turns=1,
        run_config=RunConfig(trace_include_sensitive_data=c.trace_content),
    )
    plan = planned.final_output
    if not isinstance(plan, _TopicPlan):
        raise RuntimeError("Topic planner returned an unexpected result")
    for skill in plan.new_skills:
        if any(len(criterion) > 500 for criterion in skill.success_criteria):
            raise ValueError(
                "Skill success criteria must each be at most 500 characters"
            )
    with c.store.savepoint():
        result = c.store.establish_topic(
            c,
            {"language": target_language, **topic.model_dump()},
            _existing_skill_ids(plan.existing_skill_keys, candidates),
            [item.model_dump() for item in plan.new_skills],
            [item.model_dump() for item in plan.prerequisites],
            [item.model_dump() for item in plan.links],
            plan.initial_focus.model_dump(),
        )
    return result


@function_tool(failure_error_function=tool_error)
async def expand_topic(
    ctx: RunContextWrapper[Context], expansion: ExpandTopicInput
) -> dict:
    """Add justified extension/context skills to an existing topic's reusable skill graph."""
    c = ctx.context
    c.check()
    for skill in expansion.new_skills:
        if any(len(criterion) > 500 for criterion in skill.success_criteria):
            raise ValueError(
                "Skill success criteria must each be at most 500 characters"
            )
    with c.store.savepoint():
        return c.store.expand_topic(
            c,
            expansion.topic_id,
            expansion.existing_skill_ids,
            [item.model_dump() for item in expansion.new_skills],
            [item.model_dump() for item in expansion.prerequisites],
            [item.model_dump() for item in expansion.links],
            expansion.rationale,
        )


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
async def set_learning_focus(
    ctx: RunContextWrapper[Context], focus: FocusInput
) -> dict:
    """Set the session-wide active topic and its 1–3 target skills plus support skills."""
    c = ctx.context
    c.check()
    return c.store.set_focus(
        c,
        focus.topic_id,
        focus.target_skill_ids,
        focus.supporting_skill_ids,
        focus.reason,
    )


@function_tool(failure_error_function=tool_error)
async def present_exercise(ctx: RunContextWrapper[Context], exercise: Exercise) -> dict:
    """Persist and queue a multi-skill exercise card; the application renders it exactly."""
    c = ctx.context
    c.check()
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
    """Save the actual learner reply and per-skill observations for a prior exercise."""
    c = ctx.context
    c.check()
    if c.selected_exercise_id and c.selected_exercise_id != assessment.exercise_id:
        raise ValueError("Assessment must match the selected exercise answer")
    result = c.store.assess_attempt(
        c,
        assessment.exercise_id,
        assessment.feedback,
        [item.model_dump() for item in assessment.observations],
    )
    c.assessments.append(result)
    return result


@function_tool(failure_error_function=tool_error)
async def recall_learning_context(ctx: RunContextWrapper[Context]) -> dict:
    """Recall bounded profile, topic graph, focus, exercise, and evidence summaries."""
    c = ctx.context
    c.check()
    return c.store.prompt_state(c.learner)


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
    establish_topic,
    expand_topic,
    supersede_skills,
    set_learning_focus,
    present_exercise,
    record_assistance,
    assess_attempt,
    recall_learning_context,
    retrieve_source,
    save_pasted_source,
    get_source_excerpt,
]
