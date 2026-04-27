# Contract: State Prompt Builders

**Files**: `src/milai/llm/prompts/*.py`
**Type**: Pure Python builder functions plus Pydantic response models
**Purpose**: Keep LLM prompt construction explicit, testable, and owned by the handler that uses it. State handlers call pure prompt builders, then pass returned messages to `LLMClient`; prompt builders never call providers directly, and persisted `AppState` variants never contain prompt behavior.

---

## Contract Definition

Prompt builders return provider-neutral messages:

```python
from milai.llm.types import Message
from milai.models.user_state import UserState
from milai.state.variants import AppState

def build_prompt(state: AppState, user: UserState, **context: object) -> list[Message]:
    """Return the complete message list for one LLM call."""
```

Each concrete builder should use typed arguments instead of a generic `AppState` when a narrower state is known:

```python
def build_question_prompt(
    state: AssessmentState,
    user: UserState,
) -> list[Message]: ...
```

Structured prompt modules define the Pydantic model passed to `LLMClient.complete(..., response_model=...)`.

---

## Required Builders

| App state | Module | Builder | LLM method | Response model | Required context |
|---|---|---|---|---|---|
| `AssessmentState` | `assessment.py` | `build_question_prompt` | `complete` | `AssessmentQuestionBatch` | profile, prior answers, current difficulty, assessed skill topics |
| `AssessmentState` | `assessment.py` | `build_fluency_prompt` | `complete` | `FluencyResult` | profile, completed assessment answers, assessed skill topics |
| `CurriculumGenerationState` | `curriculum.py` | `build_generation_prompt` | `complete` | `CurriculumDraft` | profile, fluency level, learning goal, available time, initial skills |
| `CurriculumReviewState` | `curriculum.py` | `build_adjustment_prompt` | `complete` | `CurriculumDraft` | current curriculum, user free-text feedback, removed/reordered modules |
| `LessonState` | `lesson.py` | `build_lesson_prompt` | `complete` | `LessonContent` | active lesson/topic, profile, curriculum position, top SRS review skills |
| `LessonState` | `feedback.py` | `build_feedback_prompt` | `complete` | `ExerciseFeedback` | exercise, user answer, expected topics, profile, current lesson context |
| `LessonState` | `lesson.py` | `build_dynamic_change_prompt` | `complete` | `LessonContent` or `CurriculumPatch` | current lesson, requested skip/add-topic/difficulty change, curriculum cursor |
| `DeviationState` | `deviation.py` | `build_chat_prompt` | `chat` | raw assistant text | lesson context, profile, bounded context window, off-topic boundary instructions |
| `CurriculumCompleteState` | `curriculum.py` | `build_extension_prompt` | `complete` | `CurriculumDraft` | completed curriculum summary, skill strengths, learner goal |

States without entries in this table must not call `LLMClient`.

---

## Contract Rules

1. **Pure builders**: builders must not read files, environment variables, terminal input, storage, or provider config.
2. **Provider-neutral output**: builders return `list[Message]`; provider-specific request options stay in `LLMClient`.
3. **No secrets**: generated messages must never include API keys, config file paths containing secrets, or raw environment values.
4. **Explicit context**: all required context must be passed through typed function arguments. No module-level mutable context.
5. **Schema ownership**: structured builders own the response model they ask `LLMClient.complete()` to validate.
6. **State boundary**: each builder should include only the active state's needed context plus stable `UserState` learning context.
7. **SRS injection by value**: lesson and feedback prompts receive ranked `Skill` values; they do not call scheduler functions directly.
8. **Preference handling**: user preferences are passed as explicit `teaching_preferences`; prompt builders do not parse free-form preference values.
9. **Deviation boundary**: deviation prompts include the rolling context window, the lesson context, and explicit instructions to keep conversation bounded to language learning.
10. **Deterministic tests**: unit tests must be able to assert message content and schema validation without network calls.
11. **Handler ownership**: prompt selection lives in the relevant state handler. There must be no central state-to-prompt registry and no prompt-builder methods on persisted `AppState` models.

---

## Test Requirements

`tests/contract/test_state_prompts_contract.py` verifies:

- every LLM-backed state has a prompt builder listed in this contract
- every structured builder has a response model
- every builder returns at least one system message and one user/context message
- no builder output contains placeholder template text or known secret keys
- prompt output schemas reject malformed LLM responses

Unit prompt tests verify state-specific behavior:

- `test_assessment_prompts.py`: assessment questions include target language, prior answers, difficulty, and skill-topic expectations
- `test_curriculum_prompts.py`: generation, adjustment, and extension prompts include profile, fluency, curriculum context, and user feedback where applicable
- `test_lesson_prompts.py`: lesson and dynamic-change prompts include curriculum position, requested change, and top review skills
- `test_feedback_prompts.py`: feedback prompts include exercise text, answer, expected skill topics, and contextual explanation requirements
- `test_deviation_prompts.py`: chat prompts include bounded context window, lesson-return behavior, and off-topic guardrails
