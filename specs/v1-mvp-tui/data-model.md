# Data Model: milai

**Branch**: `v1-mvp-tui` | **Date**: 2026-04-24

---

## Overview

Two separate structures are persisted together in `~/.milai/state.json` under two top-level keys:

- **`UserState`** — the user's learning domain data: profile, skills, curriculum. No workflow information. Could be loaded and inspected independently of the application.
- **`AppState`** — the application's current workflow state: a discriminated union where each variant carries only the payload relevant to that state.

Keeping them separate means `UserState` is never polluted with workflow concerns, and `AppState` never carries domain data. The state machine receives both as independent arguments.

```json
{
  "user": { ... },
  "app":  { "type": "deviation", "history": [...], "lesson_context": "..." }
}
```

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

---

## AppState — Discriminated Union

The workflow state of the application. Entirely independent from `UserState` — it carries no domain data, only what the state machine needs to know about *where* the application is and what *transient context* that position requires.

Each variant has a `type` literal discriminator field for Pydantic serialisation. Variants with no payload are empty dataclasses; their `type` field alone identifies the state.

```
OnboardingState          { type: "onboarding" }
AssessmentState          { type: "assessment",        ...payload }
AssessmentReviewState    { type: "assessment_review", ...payload }
CurriculumGenerationState{ type: "curriculum_gen" }
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

Resumption: if `current_idx > 0`, the state machine offers to resume from that question. On completion, `fluency_level` is extracted to `UserProfile` and the raw Q&A is archived to `history.db`; the state transitions to `AssessmentReviewState`.

### AssessmentReviewState payload

```
├── fluency_level: str                   # e.g. "A2", "Intermediate" — pending user confirmation
└── fluency_rationale: str               # LLM explanation shown to the user
```

Once the user confirms (or overrides), `fluency_level` is written to `UserProfile.fluency_level` and the state transitions to `CurriculumGenerationState`. The payload is consumed and does not persist beyond this state.

### DeviationState payload

```
├── history: list[Message]               # rolling LLM context window (max 10 exchanges)
└── lesson_context: str                  # title of the lesson the deviation occurred during
```

`history` is the live buffer for building the next LLM prompt. Each exchange is written to `history.db` as a `DeviationExchangeEvent` before being appended here. The DB is the permanent record; this buffer avoids querying the DB on every turn. On `DeviationState` → `LessonState` transition, the payload is dropped; the lesson cursor is unchanged in `Curriculum`.

### All other states

`LessonState`, `CurriculumReviewState`, `CurriculumGenerationState`, `LessonCompleteState`, `CurriculumCompleteState`, `OnboardingState` carry no payload beyond their `type` discriminator. All context they need is in the global fields (`curriculum`, `skills`, `profile`).

---

## AssessmentQuestion

```
AssessmentQuestion
├── text: str                            # the question text shown to the user
├── expected_topics: list[str]           # topics this question probes (used to seed initial skills)
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
├── description: str
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

## History Log (separate from UserState)

**File**: `~/.milai/history.db` — SQLite database.

Rationale: `UserState` is the current snapshot (small, write-heavy, atomic-write matters); the history database is the unbounded chronological record (queryable, schema-enforced, indexed). SQLite is zero-dependency (`sqlite3` stdlib), handles 100k+ rows without degradation, and enforces schema on insert.

All events are rows in a single `events` table with a `event_type` discriminator column. Additional columns per event type are stored as a `payload` JSON column, keeping the schema stable as new event types are added without requiring migrations.

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    session_id  TEXT    NOT NULL,   -- UUID per app launch; groups a full session
    timestamp   TEXT    NOT NULL,   -- ISO 8601 UTC
    payload     TEXT    NOT NULL    -- JSON; schema per event_type below
);

CREATE INDEX idx_events_session  ON events(session_id);
CREATE INDEX idx_events_type     ON events(event_type);
CREATE INDEX idx_events_ts       ON events(timestamp);
```

### ExerciseAttemptEvent (`event_type: "exercise_attempt"`)

`payload` fields:
```
module_title, lesson_title, exercise_instruction, exercise_type,
user_answer, feedback, is_correct (bool | null), skill_topics (JSON array)
```

The inline `Exercise.user_answer` / `Exercise.feedback` in `UserState` reflects the *latest* attempt; the history DB preserves *all* attempts if an exercise is retried.

### DeviationExchangeEvent (`event_type: "deviation_exchange"`)

`payload` fields:
```
lesson_context, user_message, assistant_message
```

Written for each exchange turn before the rolling window is updated. Full conversation reconstructed via `SELECT ... WHERE session_id = ? AND event_type = 'deviation_exchange' ORDER BY id`.

### AssessmentExchangeEvent (`event_type: "assessment_exchange"`)

`payload` fields:
```
question, difficulty, user_answer
```

### CurriculumChangeEvent (`event_type: "curriculum_change"`)

`payload` fields:
```
change_type ("reorder" | "remove" | "feedback_adjustment" | "extension"), description
```

---

## SessionContext (in-memory only; not persisted)

```
SessionContext
├── session_id: str       # UUID generated once per app launch; used as foreign key in history.db
└── pending_retry: bool   # True if last LLM call failed and user chose retry
```

Genuinely ephemeral — a new `session_id` is generated on every launch. Everything else that was previously here (`deviation_history`, `return_state`) now lives on the `DeviationState` payload in `UserState` and is persisted normally.

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
| CurriculumCompleteState | OnboardingState | User resets / changes language |

---

## Serialisation

`state.json` has two top-level keys, `"user"` and `"app"`, each validated independently through Pydantic on load. A validation failure in either is a corrupted state file — the user is notified with a recovery prompt (backup the file, offer to start fresh).

- `datetime` fields → ISO 8601 UTC strings
- `float` fields → rounded to 4 decimal places on write
- `AppState` discriminated union → serialised via Pydantic's `model_discriminator` on the `type` field
- `None` fields → JSON `null`
