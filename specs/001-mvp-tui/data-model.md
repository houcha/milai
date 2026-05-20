# Data Model: milai

**Branch**: `001-mvp-tui` | **Date**: 2026-04-26

---

## Overview

The persisted application snapshot is a `PersistedState` document stored at `~/.milai/state.json`:

```json
{
  "user": { ... },
  "app":  { "type": "deviation", "context_window": [...], "lesson_context": "..." }
}
```

`PersistedState` contains two separate structures:

- **`UserState`** — the user's learning domain data: profile, skills, curriculum. No workflow information. Could be loaded and inspected independently of the application.
- **`AppState`** — the application's current workflow state: a discriminated union where each variant carries only the payload relevant to that state.

Keeping them separate means `UserState` is never polluted with workflow concerns, and `AppState` never carries domain data. Persisting them together atomically means the state machine can resume from an exact checkpoint, including in-progress assessment or deviation state.

---

## PersistedState

```text
PersistedState
├── user: UserState
└── app: AppState
```

`PersistedState` is the storage boundary for `StorageClient.load()` / `save()`. The state machine may work with `user` and `app` as separate in-memory values, but they are persisted and loaded as one atomic snapshot.

On launch, the application calls `StorageClient.load()` before entering the state machine:

- If no snapshot exists, the app starts from a fresh `OnboardingState`.
- If a snapshot exists, the app asks whether to continue it or start a new session.
- Continuing passes the loaded `PersistedState` into the state machine unchanged.
- Starting a new session replaces the local learning context with a fresh `UserState` and `OnboardingState`; v1 does not preserve multiple local sessions or multiple target-language tracks.

---

## UserState

```
UserState
├── profile: UserProfile                 # learner identity and preferences
├── skills: list[Skill]                  # SRS-tracked topic skills (grows over time)
└── curriculum: Curriculum | None        # None until confirmed in CURRICULUM_REVIEW
```

**Invariants**:
- `curriculum` is `None` only while the workflow is in ONBOARDING, ASSESSMENT, ASSESSMENT_REVIEW, or CURRICULUM_GENERATION.
- `skills` entries are unique by `topic` (normalised to lowercase).
- Initial skills are inferred during curriculum generation from completed assessment answers, not attached to individual assessment questions.

---

## AppState — Discriminated Union

The workflow state of the application. Entirely independent from `UserState` — it carries no domain data, only what the state machine needs to know about *where* the application is and what *transient context* that position requires.

Each variant has a `type` literal discriminator field for Pydantic serialisation. Variants with no payload are empty dataclasses; their `type` field alone identifies the state.

```
OnboardingState          { type: "onboarding" }
AssessmentState          { type: "assessment",        ...payload }
AssessmentReviewState    { type: "assessment_review", ...payload }
CurriculumGenerationState{ type: "curriculum_gen",    ...payload }
CurriculumReviewState    { type: "curriculum_review" }
LessonState              { type: "lesson" }
DeviationState           { type: "deviation",         ...payload }
LessonCompleteState      { type: "lesson_complete" }
CurriculumCompleteState  { type: "curriculum_complete" }
```

### AssessmentState payload

```
├── questions: list[AssessmentQuestion]  # LLM-generated; ordered
└── current_idx: int                     # index of next unanswered question (enables resume)
```

Resumption: if `current_idx > 0`, the state machine offers to resume from that question. On completion, `fluency_level` is extracted to `UserProfile`; the state transitions to `AssessmentReviewState`.

### AssessmentReviewState payload

```
├── fluency_level: str                   # e.g. "A2", "Intermediate" — pending user confirmation
├── fluency_rationale: str               # LLM explanation shown to the user
└── assessment_questions: list[AssessmentQuestion]  # completed evidence carried into curriculum generation
```

Once the user confirms (or overrides), `fluency_level` is written to `UserProfile.fluency_level` and the state transitions to `CurriculumGenerationState`. Completed assessment questions are carried forward so curriculum generation can infer durable skill topics from the full answer set.

### CurriculumGenerationState payload

```
└── assessment_questions: list[AssessmentQuestion]  # completed assessment evidence used to infer initial skills
```

The curriculum-generation prompt consumes the confirmed profile and completed assessment answers. It returns both the curriculum draft and initial `Skill` entries inferred at curriculum-level granularity.

### DeviationState payload

```
├── context_window: list[Message]        # rolling LLM context window (max 10 exchanges)
└── lesson_context: str                  # title of the lesson the deviation occurred during
```

`context_window` is the live buffer for building the next LLM prompt. It is capped at 10 exchanges and persisted only as part of `PersistedState` so a mid-deviation session can resume. On `DeviationState` → `LessonState` transition, the payload is dropped; the lesson cursor is unchanged in `Curriculum`.

### All other states

`LessonState`, `CurriculumReviewState`, `CurriculumGenerationState`, `LessonCompleteState`, `CurriculumCompleteState`, `OnboardingState` carry no payload beyond their `type` discriminator. All context they need is in the global fields (`curriculum`, `skills`, `profile`).

---

## AssessmentQuestion

```
AssessmentQuestion
├── text: str                            # the question text shown to the user
├── user_answer: str | None             # None until answered
└── difficulty: str                      # "beginner" | "intermediate" | "advanced"
```

---

## UserProfile

```
UserProfile
├── target_language: str                 # e.g. "Spanish", "Mandarin", "Swahili" (required)
├── native_language: str | None
├── learning_goal: str | None            # e.g. "travel", "business", "general"
├── minutes_per_day: int | None          # self-reported study time; used in curriculum pacing
├── fluency_level: str | None            # set after ASSESSMENT_REVIEW; e.g. "A2", "Intermediate"
└── preferences: dict[str, Any]          # free-form; LLM-interpretable signals
```

**`preferences` contract**: Values are strings or primitives. No nested dicts. Examples:
- `"formality": "casual"` — prefers informal speech over textbook formal
- `"explanation_style": "visual analogies"` — user's noted learning preference
- `"avoid": "grammar jargon"` — user has requested plain explanations

Passed verbatim to LLM system prompts under the key `teaching_preferences`. The LLM interprets it freely; the application does not parse it.

---

## Skill

```
Skill
├── topic: str                           # canonical topic name, lowercase (e.g. "past tense", "articles")
├── strength: float                      # 0.0 (no knowledge) → 1.0 (mastered); clamped
├── last_seen: datetime                  # UTC; updated on each encounter
├── streak: int                          # consecutive correct answers; reset to 0 on failure
├── interval_days: float                 # current review interval (SRS); starts at 1.0
└── total_encounters: int                # total times this skill has been exercised (all time)
```

**SRS update rules** (applied by `srs.scheduler`):
```
success → strength = min(1.0, strength + 0.1)
          streak += 1
          interval_days = min(90.0, interval_days * 2.0)

failure → strength = max(0.0, strength - 0.2)
          streak = 0
          interval_days = 1.0

due_for_review → (today_utc - last_seen).days >= interval_days
```

**Priority score** (used to rank skills for LLM prompt inclusion):
```
priority = (1.0 - strength) * log2(days_since_seen + 1)
```
Top-N skills by priority are included in each LLM prompt as explicit "reinforce these" instructions.

---

## Curriculum

```
Curriculum
├── current_module_idx: int              # pointer to active module (0-based)
└── modules: list[Module]
```

```
Module
├── title: str
├── current_lesson_idx: int              # pointer to active lesson within this module
└── lessons: list[Lesson]
```

```
Lesson
├── title: str
├── theory: str                          # LLM-generated explanation text
├── current_exercise_idx: int            # pointer to active exercise
└── exercises: list[Exercise]
```

```
Exercise
├── instruction: str
├── exercise_type: str                   # "translation" | "fill_blank" | "multiple_choice" | "open"
├── options: list[str] | None            # for multiple_choice only
├── user_answer: str | None
├── feedback: str | None                 # LLM-generated; None until exercise completed
├── is_correct: bool | None             # None until evaluated; None for open-ended
└── skill_topics: list[str]             # topics this exercise reinforces (used for SRS update)
```

**Progress pointers**: `curriculum.current_module_idx`, `module.current_lesson_idx`, and `lesson.current_exercise_idx` form the resume cursor.

The `confirmed` flag previously on `Curriculum` is removed — an unconfirmed curriculum simply means `state` is `CurriculumReviewState`. Once the user confirms, the state transitions to `LessonState` and the curriculum is implicitly confirmed.

---

## Snapshot-Owned Interaction State

v1 does not maintain a separate chronological event store or interaction-record model layer. Interaction details needed for resume are owned by the existing snapshot models:

- Assessment answers live on `AssessmentQuestion.user_answer` while assessment is in progress, then move through assessment review into curriculum generation for initial skill inference.
- Lesson attempts update the active `Exercise` fields (`user_answer`, `feedback`, `is_correct`) and the relevant `Skill` records.
- Deviation exchanges live in `DeviationState.context_window` only while the user is in deviation mode.
- Curriculum review changes update the active `Curriculum` directly before confirmation.

Durable chronological interaction logging is deferred to a future version if product needs debugging, analytics, or cross-session audit trails.

---

## State Transition Table

| From | To | Trigger |
|---|---|---|
| ONBOARDING | ASSESSMENT | Profile submitted |
| ASSESSMENT | ASSESSMENT (same) | User resumes incomplete assessment |
| ASSESSMENT | ASSESSMENT_REVIEW | All questions answered; fluency computed |
| ASSESSMENT_REVIEW | CURRICULUM_GENERATION | User confirms or overrides fluency level |
| CURRICULUM_GENERATION | CURRICULUM_REVIEW | LLM returns structured curriculum |
| CURRICULUM_REVIEW | CURRICULUM_REVIEW (same) | User provides feedback → LLM adjusts |
| CURRICULUM_REVIEW | LESSON | User confirms curriculum |
| LESSON | DEVIATION | User sends free-form message |
| LESSON | LessonCompleteState | All exercises in lesson answered |
| DeviationState | LessonState | User signals return (or LLM offers return, user accepts) |
| LessonCompleteState | LessonState | Advance cursor; next lesson exists |
| LessonCompleteState | CurriculumCompleteState | No more lessons in curriculum |
| CurriculumCompleteState | CurriculumGenerationState | User requests extension modules |
| CurriculumCompleteState | OnboardingState | User starts a new local session after completion |

---

## Serialisation

`state.json` has two top-level keys, `"user"` and `"app"`, each validated independently through Pydantic on load. A validation failure in either is a corrupted state file — the user is notified with a recovery prompt (backup the file, offer to start fresh).

- `datetime` fields → ISO 8601 UTC strings
- `float` fields → rounded to 4 decimal places on write
- `AppState` discriminated union → serialised via Pydantic's `model_discriminator` on the `type` field
- `None` fields → JSON `null`
