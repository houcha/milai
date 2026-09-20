# Architecture

`CLI/Web -> Tutor -> OpenAI Agents SDK Runner -> Gemini OpenAI-compatible API`

Milai has one learner-facing conversational agent. It discovers intent, maintains a
learning focus, explains, exercises, assesses, and adapts. A nested read-only topic
planner uses High reasoning exactly once before each new topic is established; normal
interaction uses Low reasoning. The planner proposes a minimum viable skill graph but
cannot write state. This keeps the conversation coherent without asking separate
agents to hand off learner context.

## Learning model

A **skill** is a learner- and language-scoped ability that can be taught and observed,
such as English past simple formation or German accusative indefinite articles. It is
independent of any topic. A **topic** supplies application context, such as discussing
Rammstein songs or ordering food, and references reusable skill IDs with `core`,
`extension`, or `contextual` roles. Prerequisite edges form a directed acyclic graph.

Every new topic starts with the minimum 3–8 core skills needed for basic understanding.
The graph expands only as the learner advances or their purpose changes. There is one
learner-wide active focus: a topic, 1–3 target skill IDs, and optional supporting skill
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
| New-topic reasoning | `consult_topic_planner` | Requires target language and purpose; read-only, High reasoning, once per turn |
| Create a topic graph | `establish_topic` | Requires planner consultation; atomically creates missing independent skills, DAG edges, topic links, and focus |
| Grow or repair the graph | `expand_topic`, `supersede_skills` | Requires learner-owned topic/skill references; validates duplicates, replacements, and cycles |
| Move the pointer | `set_learning_focus` | Requires a learner-owned topic; target and support IDs must belong to it |
| Structured teaching | `present_theory`, `present_exercise` | Requires an active focus; persists exact learner-facing artifacts and queues them for rendering |
| Help and evidence | `record_assistance`, `assess_attempt` | Requires an explicitly referenced, previously presented exercise; both are skill-specific |
| Bounded recall | `recall_learning_context` | Always; returns the same bounded state shape used by the prompt |
| Source handling | `retrieve_source`, `save_pasted_source`, `get_source_excerpt` | Always; retrieval remains learner-authorized and excerpts are bounded |

`establish_topic` is deliberately a composite command to reduce model round trips while
preserving normalized entities. A successful call still stores skills separately from
topics. `plan_teaching_action` is absent: adaptation is expressed by graph/focus changes
and the theory or exercise that implements them, so a detached rationale record cannot
claim a later action it does not identify.

## Structured replies and transactions

`Tutor.respond` returns `{text, activities}`. The final model text contains framing,
feedback, or a question. A theory lesson or exercise is complete only after its
presentation tool persists the exact content. The run context records presentation
IDs in tool-call order. When the model finishes, the same SQLite transaction saves the
turn and ordered presentation links; the web and CLI load the persisted artifacts and
render them verbatim. A failed or timed-out run rolls back learning writes, artifacts,
events, and transcript together. Per-tool savepoints also prevent a correctable graph
error from leaving partial entities while the model retries.

An attempt can reference only an exercise from an earlier turn. The server stores the
actual current learner message. Each observation references one exercise skill; skills
the response did not reveal remain unobserved. Independent success requires a successful
observation, an unscaffolded exercise, and no recorded assistance for that skill. Help
on one skill does not erase independent evidence for another skill in the same task.

## Storage, replay, and schema lifecycle

SQLite schema 2 uses normalized tables for facts, sources, skills, prerequisites,
supersessions, topics, topic links, focus history, theory, exercises, assistance,
attempts, skill observations, sessions, turns, ordered presentations, and audit events.
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
timestamp before creating schema 2. There is no implicit migration or deletion.

## Source and observability boundaries

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
