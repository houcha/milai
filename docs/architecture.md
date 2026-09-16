# Architecture

`CLI -> Tutor service -> Agents SDK Runner -> Gemini OpenAI-compatible Chat Completions`

The Runner exposes typed tools for profile facts, provisional curriculum revisions,
source retrieval, exercise creation, assistance recording, evidence, and teaching
decisions. An application-created context owns learner/session identifiers; the
model cannot choose another learner or a database path. Prompt files own pedagogy.
Python owns validation, authorization, budgets, persistence and network access.
Interaction uses Low reasoning effort. An optional read-only planning consultation
uses High, at most once per turn, with the same configured model.

## Agent loop and tool boundary

One call to `Tutor.respond` is one learner turn, but `Runner.run` may make several
model calls. A model call can return tool calls instead of a learner-facing answer.
The Runner executes those tools, appends their results to the model input, and calls
the model again. The run ends when the model returns final text without more tool
calls. Consequently, two `turn` or `generation` spans inside one application trace
usually represent two iterations of this internal loop, not two learner messages.

The final model text is the learner-facing interface. Tools are typed boundaries for
retrieval, private consultation, and durable learning state; they are not an exhaustive
list of everything the tutor can say or do. In particular:

| Chosen behavior | Tool work before the final text |
| --- | --- |
| General explanation, clarification, or question | None, unless another persistence rule applies |
| Present a task for a future learner attempt | `create_exercise` |
| Give a hint, explanation, or answer for an active exercise | `record_assistance` |
| Assess the current answer to an existing exercise | `record_evidence` |
| Adapt teaching from stored evidence | `plan_teaching_action`, followed by the chosen explanation, exercise, review, or challenge |
| Retain stated preferences or a provisional outline | `remember_profile` or `revise_curriculum` |
| Use learner-selected material | `retrieve_source` or `save_pasted_source` before relying on it |
| Seek extra reasoning for a difficult decision | `deliberate_teaching_plan`; its result is private advice and saves nothing |

The persistence tools form normalized, composable records rather than repeating all
context on every record. Assistance and assessments explicitly reference an exercise;
a teaching action explicitly references the evidence that motivated it. All writes in
one learner turn also share a turn ID and transaction. This establishes provenance and
atomicity without imposing a fixed teaching sequence.

Composition has a deliberate limit: a `teaching_action` record does not identify the
specific later exercise or final prose that implements it. Their shared turn records
co-occurrence, while the prompt asks the model to keep the declared decision and its
execution consistent. That consistency is a quality-evaluation target, not a database
invariant. Likewise, multiple independent tool calls may arrive in one model response;
a call that needs an ID returned by another tool must wait for a later model iteration.

## State and consistency

SQLite stores learner-owned sessions, replayable SDK conversation history, profile
facts, curricula, sources, exercises, assistance, evidence, and teaching actions.
An append-only event log makes changes inspectable. Tool writes are staged in a
per-turn transaction and committed with the conversation only after a successful
run. A failed turn rolls back so a retry cannot leave partial learning evidence.
Each run has a bounded duration, model turns, input size, history size and tool calls.
Invalid model tool arguments and opaque missing/wrong-kind record references return
sanitized, no-write tool errors for correction within those limits. Authorization,
database, resource-limit, and unexpected failures remain fatal and roll back the turn.
History is retained in storage; only complete recent turns are replayed into context.
Cross-session evidence is supplied separately, preserving learning beyond chat windows.

Exercises record the task and skill before evaluation. Assistance is recorded per
exercise, and evidence cannot label an answer independent when help is recorded.
The server captures the actual current learner message as evidence; the model supplies
assessment and rationale. Neither assessment correctness nor whether every hint was
recorded can be guaranteed by schema validation; these are quality-evaluation targets.

## Source boundary

Retrieval accepts learner-supplied or previously retained public HTTPS URLs, uses
bounded reads/timeouts, checks DNS addresses,
pins the connection to a validated public address, and disallows redirects. It sends
no application credentials, cookies or ambient proxies. HTML is converted to text;
unsupported, oversized or inaccessible sources return explicit failure status.
Store URL, retrieval time, content hash, excerpt and availability. Pasted material
retains a learner-provided label and is not represented as independently verified.
Fetched content never grants tools or changes system instructions.

## Observability

Langfuse's supported `OpenAIAgentsInstrumentor` captures framework model/tool spans.
Disable the default OpenAI trace exporter, not the Agents tracing mechanism used by
the integration. Add one application turn span with pseudonymous session/learner IDs,
prompt hash and committed event IDs, not duplicate model or tool spans. Hide content
by default at the instrumentation boundary. Flush before a short-lived process exits.
Tracing is optional for local use but required in the live acceptance demonstration
when credentials are available. Export/authentication and server ingestion are separate
checks; a mocked exporter is not proof of live Langfuse delivery.
Extend Langfuse's default export filter for exactly the `milai.application` scope so
the application root and learning-event references survive export. Propagate session,
learner, prompt version and trace name before starting the root span.

## Documentation consulted

- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk)
- [Models and providers](https://developers.openai.com/api/docs/guides/agents/models)
- [Results and state](https://developers.openai.com/api/docs/guides/agents/results)
- [Langfuse supported Agents integration](https://langfuse.com/integrations/frameworks/openai-agents)
- [Langfuse export filtering](https://langfuse.com/docs/observability/sdk/advanced-features#filtering-by-instrumentation-scope)

Consulted using the OpenAI developer documentation MCP and Langfuse documentation MCP.
Exact Python adapter behavior is also checked against the installed SDK source.
