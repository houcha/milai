# Architecture

`CLI/Web -> Tutor -> OpenAI Agents SDK Runner -> Gemini OpenAI-compatible API`

Milai has one learner-facing conversational agent. It discovers intent, maintains a
learning focus, explains, exercises, assesses, and adapts. When it calls
`establish_topic`, that tool invokes a nested read-only planner with High reasoning and
structured output; normal interaction uses Low reasoning. The application validates and
persists the proposed graph atomically. The planner cannot write state or talk to the
learner. This keeps the conversation coherent without asking separate agents to hand
off learner context.

## Learning model

A **skill** is a learner- and language-scoped ability that can be taught and observed,
such as English past simple formation or German accusative indefinite articles. It is
independent of any topic. A **topic** supplies one coherent application context derived from the learner’s
goals or chosen material, and references reusable skill IDs with `core`,
`extension`, or `contextual` roles. Prerequisite edges form a directed acyclic graph.

Every new topic starts with the minimum 3–8 core skills needed for basic understanding.
The graph expands only as the learner advances or their purpose changes. There is one
session-wide active focus: a topic, 1–3 target skill IDs, and optional supporting skill
IDs. Exercises reference a set of skills with `target` or `supporting` roles because a
real task usually draws on several abilities. Context never becomes a vague skill.

Skills are versioned rather than edited in place. A split, merge, or redefinition marks
old definitions superseded, records explicit old-to-new relations, and repoints topic
and active-focus links. Old attempts and observations retain their original skill IDs.
Progress is a summary of observation counts, outcomes, assistance, recency, and
application contexts. The app does not infer a mastery stage or numeric score.

## Agent loop and stable tools

One `Tutor.respond` call is one learner turn. The Runner may make several model calls:
a generation can request one or more tools, the SDK executes them, appends results, and
calls the model again until it emits final text. Multiple generation spans therefore do
not mean multiple learner messages. `ToolExecutionConfig(max_function_tool_concurrency=1)`
serializes local writes even if a provider returns several independent calls together.
Calls that need an ID from another result must still occur in a later generation.

The tutor receives one stable tool inventory on every model iteration. Applicability
is part of each tool contract and is validated again by the application and storage.
This keeps control flow visible in one place and avoids an implicit state machine made
from dynamic tool predicates. Premature or invalid calls return a bounded, no-write
error that the model can correct within the existing turn and tool budgets:

| Capability | Tool | Precondition and effect |
| --- | --- | --- |
| Explicit profile memory | `record_learner_facts` | Always; batches facts with exact quotes from the current message |
| Reuse existing abilities | `search_skills` | Always; searches active learner-owned skill definitions |
| Create a topic graph | `establish_topic` | Requires target language and purpose; internally plans, validates, and atomically creates skills, DAG edges, topic links, and focus |
| Grow or repair the graph | `expand_topic`, `supersede_skills` | Requires learner-owned topic/skill references; validates duplicates, replacements, and cycles |
| Move the pointer | `set_learning_focus` | Requires a learner-owned topic; target and support IDs must belong to it |
| Structured exercise | `present_exercise` | Requires an active focus; persists the exact task and its skill contract for later assistance and assessment |
| Help and evidence | `record_assistance`, `assess_attempt` | Requires an explicitly referenced, previously presented exercise; both are skill-specific |
| Bounded recall | `recall_learning_context` | Always; returns the same bounded state shape used by the prompt |
| Source handling | `retrieve_source`, `save_pasted_source`, `get_source_excerpt` | Always; retrieval remains learner-authorized and excerpts are bounded |

`establish_topic` is deliberately a composite command. Its public input is only the
topic name and purpose. Target language comes from persisted learner facts, and the
private planner receives those values plus saved profile values (including free-form
`level`), the bounded active skill catalog, and progress summaries for only those
candidate skills. Summaries use stable skill keys rather than database IDs and
preserve the distinction between assisted and independent success. Missing level
and evidence remain valid: discovery is a prompt policy, not a tool precondition. Its typed
output is validated before storage writes begin. A successful call still stores skills
separately from topics. `plan_teaching_action` is absent: adaptation is expressed by
graph/focus changes and the explanation or exercise that implements them, so a detached
rationale record cannot claim a later action it does not identify.

## Structured replies and transactions

The web conversation opens a presented task only through **Start exercise**. Its
temporary exercise view hides the conversation and learning sidebar while retaining
the chat scroll position and unsent drafts in browser memory. Answer actions use
the ordinary tutor transaction and persist learner-facing turns. New exercises
store a private hint with the task. Revealing it records assistance locally and
does not call the model; older exercises without a stored hint use the tutor turn.
The selected
exercise ID and action are application context, separate from learner text; assessment
tools may save observations only for an answer to that exercise. A response with no
saved assessment remains a clarification. Review writes one idempotent explanation
assistance event for every exercise skill without a model call or conversation turn.
Exercise status is rebuilt from attempts and assistance on reload; a successful latest
assessment closes the task. Feedback and hint delivery protect later retries with
assistance while leaving the assessment just completed unchanged.

`Tutor.respond` returns `{text, activities}`. The final model text carries explanations,
examples, feedback, framing, and questions without a separate theory schema. Exercises
remain structured because later attempts and assistance need a stable ID and exact skill
contract. The run context records exercise IDs in tool-call order. When the model
finishes, the same SQLite transaction saves the transcript and exercise presentation
links; the web and CLI render the persisted tasks verbatim. A failed or timed-out run
rolls back learning writes, exercises, events, and transcript together. Per-tool
savepoints also prevent a correctable graph error from leaving partial entities while
the model retries.

An attempt can reference only an exercise from an earlier turn. The server stores the
actual current learner message. Each observation references one exercise skill; skills
the response did not reveal remain unobserved. Independent success requires a successful
observation, an unscaffolded exercise, and no recorded assistance for that skill. Help
on one skill does not erase independent evidence for another skill in the same task.

## Storage, replay, and schema lifecycle

SQLite schema 3 uses normalized tables for facts, sources, skills, prerequisites,
supersessions, topics, topic links, focus history, exercises, assistance,
attempts, skill observations, sessions, turns, ordered exercises, and audit events.
Opaque IDs are always checked against the application-injected learner. The model
cannot choose a learner, session, database, or event provenance.

The model receives at most six learner-facing turns or 20,000 characters. Raw SDK tool
traffic is retained for inspection but never replayed. Dynamic state is capped at
16,000 characters and contains current profile values, topic summaries, the active
topic graph, current focus and exercise, evidence summaries, and at most five recent
focus observations. Full source bodies are excluded; the model requests bounded
excerpts when needed. If space is tight, other-topic summaries, older observations,
and source metadata are removed before the active core graph.

Schema changes are explicit. Opening a legacy or unknown database fails with a command
to run `milai reset --yes`. Reset archives the database and WAL/SHM sidecars with a UTC
timestamp before creating schema 3. There is no implicit migration or deletion.

## Source and observability boundaries

Each Gemini HTTP request has a 120-second timeout; a complete tutor turn has a
300-second limit. These limits cover slow sequential model generations without
retrying a timed-out request. A failed turn rolls back its learning writes.

Retrieval accepts learner-supplied or previously retained public HTTPS URLs, uses
bounded reads and timeouts, validates public DNS addresses, pins the connection, and
disallows redirects. It sends no application credentials, cookies, or ambient proxy
configuration. Source content is untrusted data and never grants tools or changes
instructions.

Langfuse's supported `OpenAIAgentsInstrumentor` exports framework model and tool spans;
it is instrumentation around SDK internals, not application control flow. Milai adds one
application turn span containing pseudonymous IDs, prompt hash, and committed event IDs.
Content is hidden by default. Generation input/output appears on the generation span
when content tracing is enabled; session-level trace rows need not duplicate it.

## References

- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk)
- [Agents results and state](https://developers.openai.com/api/docs/guides/agents/results)
- [Langfuse Agents integration](https://langfuse.com/integrations/frameworks/openai-agents)

The implementation is also checked against the installed Agents SDK because provider
adapter behavior can evolve between releases.

## Browser navigation

Conversation and Skills belong to the selected session. A separate Sessions view
owns create/select/rename/delete controls. The topic sidebar is chronological
(`created`, then insertion order), with the current focus highlighted. Topic clicks
navigate to the original assistant turn without a model call or focus mutation.
`topic_anchors` maps topic IDs to committed turn IDs using session-scoped audit events;
browser conversation items and tutor replies expose `turn_id` for DOM anchors.
Missing historical anchors are reported as unavailable. Model-history replay is
unchanged. Temporary exercises hide the path and require review tracking before
navigation reveals learning content. No schema migration is needed.
