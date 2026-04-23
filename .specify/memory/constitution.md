<!--
  SYNC IMPACT REPORT
  Version change: 2.0.0 → 3.0.0
  Removed principles: VI. Conventional Commits (relocated to CLAUDE.md — commit workflow is agent/tooling
                       guidance, not an engineering principle)
  Templates reviewed:
    ✅ .specify/templates/plan-template.md — no changes needed
    ✅ .specify/templates/spec-template.md — no changes needed
    ✅ .specify/templates/tasks-template.md — no changes needed
  Follow-up TODOs: Document UV toolchain commands and conventional commits in CLAUDE.md
-->

# milai Constitution

## Core Principles

### I. Test-First
Write tests before implementation. The default cycle is RED (failing test) → GREEN (minimum
implementation) → REFACTOR. When a unit of work is exploratory or a spike, that scope MUST
be explicitly acknowledged upfront; any resulting code MUST be covered by tests or discarded
before the work is merged.

**Rationale**: Tests written after implementation tend to validate what the code does rather
than what it should do. Fixing the order fixes the feedback loop.

**Exception rule**: Exploratory work is not exempt from eventual test coverage — it is only
exempt from the strict write-test-first ordering, provided the exception is declared and
resolved at merge time.

### II. Evidence-Based Validation
A task is complete when the expected behaviour is confirmed with realistic inputs end-to-end —
not when code compiles, not when unit tests pass in isolation. Bugs MUST be reproduced with a
failing test before any fix is written.

**Rationale**: Code that passes its own tests can still fail in context. Requiring real-input
verification closes the gap between "tests pass" and "done."

**Decision rule**: If you cannot show the feature working with real data, it is not done.
If you cannot show the bug reproducing in a test, the root cause is not yet understood.

### III. DRY (Don't Repeat Yourself)
Stable, repeated logic MUST live in a single named module. Extract when a pattern has appeared
in three or more places AND the abstraction is stable and clearly named.

**Rationale**: Duplication of stable logic forces every future change to be applied in
multiple places, creating drift and defects.

**Tradeoff with YAGNI**: Do not extract prematurely to prevent future duplication — that is
speculation, not DRY. Prefer temporary duplication while requirements are still evolving.
Extract once the pattern has stabilised. When DRY and YAGNI conflict, YAGNI wins at the
abstraction level; DRY wins once the pattern is confirmed stable.

### IV. YAGNI (You Aren't Gonna Need It)
Implement only what the current spec requires. When choosing between a simpler and a more
flexible design, choose simpler unless the spec explicitly requires the flexibility today.

**Rationale**: Unused flexibility adds cognitive load and maintenance cost without delivering
value. Every abstraction not required by the spec is a liability until proven otherwise.

**Tradeoff with DRY**: See Principle III. YAGNI governs when to introduce an abstraction;
DRY governs when duplicated, stable logic must be consolidated.

### V. Provider Interface
Any dependency on an external service — AI provider, remote API, or data store outside the
application boundary — MUST be mediated by an interface defined by the consuming code.
Feature code MUST NOT import or reference a concrete provider implementation directly.

**Rationale**: Interfaces decouple feature logic from external volatility, enable mocking in
tests, and make provider substitution a configuration change rather than a code change.

**Decision rule**: Before writing feature code that calls an external service, define the
interface first. The interface is owned by the feature; the provider is a plugin.

## Governance

This constitution supersedes all other practices and preferences. When a principle conflicts
with an implementation convenience, the principle wins. Exceptions must be explicitly
justified in the PR description; unjustified exceptions are a review failure.

- All code reviews MUST verify compliance with these principles
- Complexity or exception violations require explicit justification in the PR description
- Amendments require: documented rationale, version bump, and updated dependent templates
- Constitution version follows semantic versioning:
  - MAJOR: principle removal or incompatible redefinition
  - MINOR: new principle or material guidance addition
  - PATCH: clarifications, wording, or non-semantic refinements

**Version**: 3.0.0 | **Ratified**: 2026-04-24 | **Last Amended**: 2026-04-24
