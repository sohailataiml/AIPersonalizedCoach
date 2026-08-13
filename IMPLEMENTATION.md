# IMPLEMENTATION.md

# Future Coach Intelligence Platform — Implementation Plan

## 1. Objective

Build the Future candidate-assessment application in one working day while maximizing the dimensions the reviewers explicitly evaluate:

1. graph and ontology modeling
2. concept resolution
3. deterministic graph-derived safety
4. full-stack product usefulness
5. clean system/API boundaries
6. developer experience
7. communication and trade-offs
8. ability to make good decisions under ambiguity

The implementation should feel intentionally scoped, not unfinished.

---

# 2. Definition of Done

The submission is done when a reviewer can:

1. run the project locally with one primary command
2. open a coach dashboard for the supplied synthetic member
3. see the member's goals, injuries, equipment, adherence, and context
4. enter a workout request and duration
5. generate a structured warmup/main/cooldown plan
6. see knee/equipment/exclusion safety applied via graph traversal
7. inspect why exercises were selected or filtered
8. interactively change the prompt and see graph-driven changes
9. ask the copilot member-specific questions
10. render at least one useful trend chart
11. run resolver and safety tests
12. read a staff-level README explaining architecture and trade-offs

---

# 3. Scope

## Must Have

- Next.js coach dashboard
- FastAPI backend
- Movement/Clinical KG
- Member Context KG
- ingestion from provided JSON
- concept resolver
- deterministic safety engine
- workout generation workflow
- provenance trace
- AI copilot
- adherence/sleep or similar chart
- tests for concept resolver
- tests for safety filter
- Docker Compose
- README
- ARCHITECTURE.md

## Should Have

- LangGraph orchestration
- post-LLM safety validation
- graph provenance inspector
- quick-prompt palette
- mocked coach login
- typed frontend API client

## Nice to Have

Only after all must-haves work:

- streaming responses
- graph visualization
- tracing UI
- evaluation harness
- richer SNOMED grounding
- more synthetic members

---

# 4. Recommended Stack

```text
Frontend
- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- Recharts

Backend
- Python 3.12+
- FastAPI
- Pydantic v2
- LangGraph
- Neo4j Python driver
- rapidfuzz
- sentence-transformers or provider embeddings
- pytest

Infra
- Docker Compose
- Neo4j

LLM
- OpenAI or Anthropic behind a provider interface
```

---

# 5. Phase 0 — Repository Bootstrap

## Tasks

Create:

```text
frontend/
backend/
data/
scripts/
docker-compose.yml
.env.example
Makefile
ARCHITECTURE.md
IMPLEMENTATION.md
README.md
```

Copy the provided:

```text
data/exercises.json
data/member-context.json
```

Requirements:

- never add real member data
- `.env` ignored
- `.env.example` contains no secrets

## One-command target

Prefer:

```bash
make dev
```

which starts:

- Neo4j
- FastAPI
- Next.js

Alternative:

```bash
docker compose up --build
```

---

# 6. Phase 1 — Domain Models

Create typed backend models before graph logic.

Suggested files:

```text
backend/app/domain/exercise.py
backend/app/domain/member.py
backend/app/domain/workout.py
backend/app/domain/resolution.py
backend/app/domain/provenance.py
```

## Workout contracts

```python
class WorkoutExercise(BaseModel):
    exercise_id: str
    name: str
    sets: int | None = None
    reps: str | None = None
    duration_seconds: int | None = None
    rest_seconds: int | None = None
    rationale: str

class WorkoutSection(BaseModel):
    name: Literal["warmup", "main", "cooldown"]
    exercises: list[WorkoutExercise]

class GeneratedWorkout(BaseModel):
    title: str
    duration_minutes: int
    sections: list[WorkoutSection]
```

## Resolution contracts

```python
class ResolvedConcept(BaseModel):
    source_text: str
    canonical_id: str | None
    label: str | None
    concept_type: str | None
    method: Literal["exact", "alias", "fuzzy", "embedding", "unresolved"]
    confidence: float
```

## Safety contracts

```python
class SafetyDecision(BaseModel):
    exercise_id: str
    status: Literal["allowed", "downranked", "excluded"]
    reasons: list[str]
    graph_paths: list[list[str]]
    score_adjustment: float = 0
```

---

# 7. Phase 2 — Neo4j + Graph Abstraction

Create:

```text
backend/app/graph/repository.py
backend/app/graph/neo4j_repository.py
backend/app/graph/queries.py
```

Use an interface so domain logic does not directly depend on the Neo4j driver.

Example:

```python
class GraphRepository(Protocol):
    async def get_concept_by_alias(...): ...
    async def get_exercises(...): ...
    async def get_injury_regions(...): ...
    async def evaluate_exercise_constraints(...): ...
    async def get_member_context(...): ...
```

This makes safety logic unit-testable with an in-memory fake.

---

# 8. Phase 3 — Ingest the Exercise Catalog

Create:

```text
backend/app/ingestion/exercises.py
scripts/seed_graph.py
```

Read every exercise from `data/exercises.json`.

Create one `Exercise` node per exercise.

For each taxonomy value, create or reuse:

```text
Muscle
AnatomicalRegion
MovementPattern
Equipment
```

Create edges:

```text
Exercise -> TARGETS -> Muscle
Exercise -> STRESSES -> AnatomicalRegion
Exercise -> HAS_PATTERN -> MovementPattern
Exercise -> REQUIRES -> Equipment
```

Preserve:

```text
priority_tier
is_bilateral
bilateral_pair_id
```

## Acceptance Test

After seeding:

- 50 Exercise nodes exist
- all catalog muscles are represented
- all catalog joints are represented
- all movement patterns are represented
- all equipment values are represented
- no duplicate canonical nodes

---

# 9. Phase 4 — Add Curated Clinical / Ontology Layer

Do not ingest full external ontologies.

Create a small curated mapping file:

```text
backend/app/ontology/mappings.yaml
```

Example:

```yaml
anatomy:
  knee:
    aliases:
      - knee
      - knee joint
      - left knee
      - right knee
    ontology:
      source: SNOMED_CT
      code: "<documented-code-if-used>"

  lumbar_region:
    aliases:
      - lower back
      - low back
      - lumbar
      - bad lower back
```

Create the critical hierarchy:

```text
Patella -> PART_OF -> Knee
Patellofemoral Joint -> PART_OF -> Knee
Knee -> PART_OF -> Lower Limb

Lumbar Spine -> PART_OF -> Lumbar Region
```

Map a small relevant subset of catalog concepts to OPE/SNOMED/COPPER concepts using SKOS-style mapping relationships or mapping properties.

Document every external mapping used.

Do not invent ontology identifiers.

If an exact external identifier is uncertain, retain a local canonical concept and document that production would complete ontology normalization.

---

# 10. Phase 5 — Ingest Member Context

Create:

```text
backend/app/ingestion/member.py
```

Read:

```text
data/member-context.json
```

Seed:

```text
Member
Goal
Preference
Injury
Equipment
WorkoutSession
AdherenceObservation
BiomarkerObservation
LabResult
DEXAResult
ChatMessage
CoachBrief
ChurnSignal
```

Keep timestamps.

Map the member's knee injury to the canonical clinical/anatomical nodes in KG1.

Map available equipment to existing Equipment nodes.

## Important

The member graph should support real queries rather than storing the source JSON as one blob.

---

# 11. Phase 6 — Concept Resolver

Create:

```text
backend/app/resolution/normalizer.py
backend/app/resolution/resolver.py
backend/app/resolution/embeddings.py
```

## Pass 1 — Exact / alias

Normalize:

```text
lowercase
strip punctuation
collapse whitespace
common abbreviations
```

Examples:

```text
DB -> dumbbell
KB -> kettlebell
low back -> lumbar region
```

## Pass 2 — Fuzzy

Use RapidFuzz.

Return:

```text
match
confidence
candidate list
```

Apply a hard threshold.

## Pass 3 — Embedding fallback

Embed canonical concept labels + aliases.

Use cosine similarity.

Only accept above threshold.

## Output

Every resolution should include:

```text
source phrase
canonical concept
method
confidence
```

## Fail Gracefully

Below threshold:

```json
{
  "source_text": "weird knee-ish thing",
  "canonical_id": null,
  "method": "unresolved",
  "confidence": 0.61
}
```

Never force a match.

---

# 12. Phase 7 — Coach Request Parsing

Create:

```text
backend/app/agents/intent.py
```

Use either:

- deterministic parsing for obvious constraints
- or structured LLM extraction followed by canonical resolution

Return:

```python
class WorkoutIntent(BaseModel):
    requested_focus: list[str]
    explicit_exclusions: list[str]
    equipment_mentions: list[str]
    injury_mentions: list[str]
    preferences: list[str]
    duration_minutes: int
```

Important:

LLM extraction is permitted here because it does not itself decide safety.

All extracted concepts still pass through the resolver.

---

# 13. Phase 8 — Deterministic Safety Engine

This is the highest-priority backend module.

Create:

```text
backend/app/safety/engine.py
backend/app/safety/policies.py
backend/app/safety/graph_paths.py
```

## Algorithm

For each exercise:

### A. Explicit exclusions

Resolve excluded term.

Traverse relevant:

```text
Exercise
MovementPattern
bilateral_pair_id / variant mapping
```

Mark matching variants `excluded`.

### B. Equipment

Query required equipment.

If a required item is not available:

```text
status = excluded
reason = unavailable equipment
```

### C. Injury

For each injury:

1. get affected region
2. compute anatomical closure using `PART_OF`
3. inspect `STRESSES` edges for exercise
4. inspect `CONTRAINDICATES`
5. derive safety decision

### D. Preferences

Adjust ranking.

Do not convert a preference into a clinical contraindication unless the domain rule explicitly says so.

---

# 14. Phase 9 — Safety Test Suite Before LLM Integration

Create:

```text
backend/tests/test_resolver.py
backend/tests/test_safety.py
```

Critical safety tests:

### Test 1

```text
Given:
Jordan has a knee injury

And:
exercise stresses a knee child region

Then:
exercise is not treated as fully safe
```

### Test 2

```text
Given:
only dumbbells and kettlebells available

Then:
barbell-only exercise is excluded
```

### Test 3

```text
Given:
coach explicitly excludes deadlifts

Then:
deadlift variations are excluded
```

### Test 4

```text
Given:
a safe dumbbell alternative exists

Then:
it remains eligible
```

### Test 5

```text
Given:
unknown clinical phrase below threshold

Then:
resolver returns unresolved rather than guessing
```

Do not proceed until these pass.

---

# 15. Phase 10 — Workout Generation

Create:

```text
backend/app/agents/workout_graph.py
backend/app/agents/workout_planner.py
backend/app/llm/client.py
```

## LangGraph State

```python
class WorkoutState(TypedDict):
    request: WorkoutRequest
    member_context: MemberContext
    intent: WorkoutIntent
    resolved_concepts: list[ResolvedConcept]
    safety_decisions: list[SafetyDecision]
    eligible_exercises: list[ExerciseCandidate]
    generated_workout: GeneratedWorkout | None
    provenance: list[ProvenanceItem]
```

## Nodes

```text
load_member
parse_intent
resolve_concepts
evaluate_safety
rank_candidates
compose_workout
validate_workout
build_provenance
```

These can be ordinary deterministic functions inside the graph.

Avoid creating fake "agents" for every function.

---

# 16. Phase 11 — LLM Workout Planner

Give the model only:

```text
member goal summary
duration
resolved workout intent
safe candidate exercises
relevant preference data
```

Do not provide filtered exercises as selectable candidates.

Require structured output.

Example instruction conceptually:

```text
Construct a 45-minute workout using ONLY the supplied candidate exercise IDs.
Return warmup, main, cooldown, sets/reps/rest.
Do not invent exercise IDs.
```

Pydantic-validate the response.

---

# 17. Phase 12 — Post-Generation Safety Gate

Every final exercise ID must be rechecked.

Pseudo-code:

```python
for item in generated_workout.all_exercises():
    decision = safety_decisions[item.exercise_id]

    if decision.status == "excluded":
        raise UnsafePlanError(...)
```

Optional:

- replace rejected item with next-ranked safe candidate
- retry once

Record:

```text
post_validation_passed
rejected_exercises
replacement_exercises
```

This is an important interview talking point.

---

# 18. Phase 13 — Provenance Builder

Create:

```text
backend/app/provenance/builder.py
```

For included items include:

```text
intent match
goal match
available equipment path
safe anatomy result
preference influence
```

For excluded items include:

```text
exercise
decision
reason
graph path
```

Example:

```text
Goblet Squat
 → STRESSES
Patellofemoral Joint
 → PART_OF
Knee

Jordan
 → HAS_INJURY
Left Knee Pain
 → AFFECTS
Knee
```

Do not make provenance a paragraph hallucinated by the LLM.

Build it from deterministic evidence, then optionally let the LLM produce a concise human-readable summary.

---

# 19. Phase 14 — Workout API

Create:

```text
POST /api/workouts/generate
```

Response:

```json
{
  "request_id": "...",
  "workout": {},
  "resolved_concepts": [],
  "filtered_exercises": [],
  "provenance": [],
  "timing": {}
}
```

Return enough metadata for the UI to demonstrate the architecture.

---

# 20. Phase 15 — Member Copilot Retrieval

Create:

```text
backend/app/copilot/router.py
backend/app/copilot/retrieval.py
backend/app/copilot/analytics.py
backend/app/copilot/service.py
```

## Supported intents

Implement a small high-quality set:

```text
SHOW_BRIEF
ADHERENCE_TREND
SLEEP_WEEK
WHAT_CHANGED
CHURN_RISK
MESSAGE_PATTERN
GENERAL_MEMBER_QA
```

## Retrieval behavior

For known intents, use deterministic graph queries and Python analytics.

Only then ask the LLM to summarize.

Example:

```text
"How is adherence trending?"
    ↓
query 4–8 weeks adherence
    ↓
calculate slope/delta
    ↓
LLM summarizes supplied numbers
```

---

# 21. Phase 16 — Copilot Charts

Return chart JSON rather than asking the LLM to emit arbitrary visualization code.

Support at least:

```text
line
bar
```

Implement:

- adherence trend
- sleep trend

Optional:

- message frequency

---

# 22. Phase 17 — Frontend Foundation

Create routes/components:

```text
frontend/app/page.tsx
frontend/components/member-header.tsx
frontend/features/workout-generator/*
frontend/features/copilot/*
frontend/features/provenance/*
```

## Member Header

Show:

```text
Jordan Rivera
primary goal
current injury
equipment
recent adherence
churn risk
```

Do not expose the raw source JSON.

---

# 23. Phase 18 — Workout Generator UI

Components:

```text
WorkoutPromptForm
DurationSelector
WorkoutPlan
WorkoutExerciseCard
FilteredExercises
ProvenanceInspector
ResolutionBadges
```

Form fields:

```text
prompt
duration
```

Useful prefilled example:

```text
Lower-body workout. Her left knee is bothering her and she only has dumbbells and a kettlebell.
```

---

# 24. Phase 19 — Provenance UX

Make this visually prominent.

For an included exercise:

```text
Dumbbell Romanian Deadlift
SAFE

✓ Dumbbell available
✓ No knee-stress rule triggered
✓ Matches hinge movement
```

For a filtered exercise:

```text
Barbell Back Squat
FILTERED

Reason:
Unavailable equipment + knee loading

Graph:
Back Squat
 → REQUIRES
Barbell

Jordan
 → DOES_NOT_HAVE
Barbell
```

And:

```text
Back Squat
 → STRESSES
Knee
```

---

# 25. Phase 20 — Copilot UI

Components:

```text
CopilotChat
QuickPrompts
ChatHistory
ChartCard
MorningBrief
```

Quick prompts:

```text
Show me the brief
How's adherence trending?
Sleep this week
What changed since last week?
```

Use the supplied chat history in the member view.

If image metadata exists in the synthetic data, render it safely as available; do not invent image contents.

---

# 26. Phase 21 — Demo Scenarios

Prepare these before polishing.

## Scenario A — Injury

Input:

```text
Create a 45-minute lower-body workout. Her left knee is bothering her.
```

Demo must show:

- `knee` resolves
- anatomy traversal occurs
- affected exercises filtered/down-ranked
- provenance paths visible

## Scenario B — Limited Equipment

Input:

```text
Build a full-body workout. She has no barbell, only dumbbells and a kettlebell.
```

Demo must show:

- barbell exercises removed
- valid alternatives selected

## Scenario C — Interactive Exclusion

Input:

```text
Use the previous workout but exclude deadlifts.
```

Demo must show:

- deadlift family removed
- graph-safe alternatives remain

---

# 27. Phase 22 — Observability

Add request-scoped logs:

```text
request_id
resolver latency
graph latency
LLM latency
total latency
concepts resolved
concepts unresolved
candidate count
filtered count
post-validation result
```

Optional:

- LangSmith/OpenTelemetry if already familiar

Do not spend time integrating observability before core functionality works.

---

# 28. Phase 23 — README

README must include:

## Overview

What problem is being solved.

## Demo

Screenshots/GIF optional.

## Architecture

Include the high-level Mermaid diagram.

## Why the knowledge graph matters

Explicitly explain:

```text
graph = authority
LLM = interpretation/composition
```

## Stack rationale

Defend:

```text
Next.js
FastAPI
Neo4j
LangGraph
LLM provider
```

## Local run

Prefer:

```bash
cp .env.example .env
make dev
```

## Data

State clearly:

```text
Only Future-provided and generated synthetic data is used.
```

## AI-assisted development

Be transparent.

Example:

```text
AI coding tools were used for implementation assistance, test generation,
and documentation refinement. Architecture, safety rules, graph semantics,
trade-offs, and final review were manually directed and validated.
```

## Trade-offs

Include:

- curated ontology subset
- simple graph schema
- one-member scope
- no production auth
- local Neo4j
- limited evaluation corpus

## Production evaluation

Include:

- safety metrics
- resolver accuracy
- grounding accuracy
- coach adoption
- graph coverage
- latency/cost

## Example scenarios

Include 2–3 exact request/response examples with provenance.

---

# 29. Phase 24 — Final Test Matrix

Run:

```text
backend unit tests
frontend typecheck
frontend tests if implemented
backend lint
frontend lint
production builds
Docker startup
graph seed from clean state
all three demo scenarios
```

Critical failure test:

Temporarily simulate an LLM response containing an excluded exercise.

Expected:

```text
post-generation safety gate rejects it
```

Capture this in a test.

---

# 30. Suggested Time Allocation

Because the assignment says one day, prioritize ruthless scope control.

```text
Hour 0–1
Architecture, repo bootstrap, data inspection

Hour 1–2
Graph schema + ingestion

Hour 2–3
Member graph + ontology subset

Hour 3–4
Concept resolver

Hour 4–5
Safety engine + tests

Hour 5–6
Workout runtime + LLM

Hour 6–7
Copilot retrieval + analytics

Hour 7–8
Frontend dashboard

Hour 8–9
Provenance UX + charts

Hour 9–10
Tests, README, demo polish
```

If running behind, cut nice-to-haves before reducing deterministic safety quality.

---

# 31. Priority Order

Never compromise the ordering below:

```text
1. deterministic safety
2. graph correctness
3. resolver
4. provenance
5. working workout generator
6. member copilot
7. UI polish
8. nice-to-haves
```

A smaller app with visible, correct graph reasoning is stronger than a broad app where the LLM secretly does the important work.

---

# 32. Claude Code Execution Rules

When using Claude Code to implement this plan:

1. Read `ASSESSMENT.md`, `ARCHITECTURE.md`, and `IMPLEMENTATION.md` first.
2. Inspect the provided JSON before changing schema assumptions.
3. Do not invent fields that contradict the supplied data.
4. Do not replace graph safety with prompt instructions.
5. Do not use vector similarity as the safety mechanism.
6. Do not let LLM output bypass post-generation safety validation.
7. Preserve provenance for every filtering decision.
8. Add tests as each critical subsystem is built.
9. Keep the app runnable throughout implementation.
10. Do not commit secrets.
11. Use synthetic data only.
12. Document ambiguous decisions rather than hiding them.

---

# 33. Stop Conditions

Do not add additional features until all are true:

```text
[ ] exercise graph seeded
[ ] member graph seeded
[ ] concept resolver tested
[ ] knee traversal tested
[ ] equipment filter tested
[ ] explicit exclusion tested
[ ] workout endpoint works
[ ] LLM cannot bypass safety
[ ] provenance visible
[ ] copilot answers supplied-member questions
[ ] at least one chart works
[ ] app starts from clean setup
[ ] README explains trade-offs
```

---

# 34. Interview Talking Points

Be prepared to explain:

### Why not let the LLM judge exercise safety?

Because generative output is probabilistic and difficult to audit. A graph query over explicit clinical/anatomical relationships is repeatable, testable, and explainable.

### Why a property graph instead of pure vector RAG?

The problem requires relationship traversal:

```text
exercise → stresses → patellofemoral joint → part of → knee
```

Semantic similarity alone does not encode that reasoning reliably.

### Why use embeddings at all?

Only for messy-language canonicalization when exact and fuzzy matching fail.

### Why not ingest full SNOMED/OPE?

The assignment is one day. A curated subset lets us demonstrate meaningful grounding and correct semantics without introducing thousands of unused concepts.

### Why post-validate the LLM result?

It turns safety from a prompt hope into a system invariant.

### What would change in production?

- reviewed clinical policies
- ontology lifecycle/versioning
- privacy and access controls
- larger evaluation datasets
- graph coverage monitoring
- model observability
- coach feedback loop
- robust tenancy
- high availability

---

# 35. Build Status (completed)

All stop conditions from §33 are met. Verified on both graph backends.

```text
[x] exercise graph seeded          50 exercises, 19 muscles, 36 patterns, 32 equipment
[x] member graph seeded            14 node types, timestamped observations
[x] concept resolver tested        43 tests
[x] knee traversal tested          PART_OF closure reaches parent joint
[x] equipment filter tested        barbell/machine exclusion + alternatives remain
[x] explicit exclusion tested      resolves to hinge family (no name matches exist)
[x] workout endpoint works         POST /api/workouts/generate, ~39 ms end to end
[x] LLM cannot bypass safety       13 post-validation tests incl. adversarial workflow
[x] provenance visible             graph paths + decision source in the inspector
[x] copilot answers questions      9 intents, grounded, refuses on missing data
[x] at least one chart works       adherence (line) and sleep (bar)
[x] app starts from clean setup    make dev / docker compose up --build
[x] README explains trade-offs     see README.md
```

Verification results: 114 backend tests pass, ruff clean, frontend typecheck and
lint clean, production build succeeds (225 kB First Load JS), graph seeds from a
clean Neo4j with count verification, and all three demo scenarios pass on both
the in-memory and Neo4j backends with identical filtering counts.

## Deviations from the original plan

1. **In-memory graph backend added** alongside Neo4j (both implement the same
   `GraphRepository` Protocol). ARCHITECTURE.md §4 anticipated this for unit
   tests; it was promoted to a first-class runtime backend so the app runs with
   zero setup. Safety logic is shared, and parity is verified.
2. **Deterministic LLM stub added** as the default provider, so the architecture
   is demonstrable without an API key.
3. **`resolve_concepts` is not a separate LangGraph node** - intent parsing
   already routes every span through the resolver, so a separate node would be
   theatre (ARCHITECTURE.md §21 warns against exactly this).
4. **`priority_tier` is not used for ranking** - it is uniformly `2` across all 50
   catalog rows and carries no signal.
5. **Side-aware injury reasoning added** beyond the plan, because the catalog's
   `side` field and the member's *left* knee injury make it meaningful.

---

## Phase 4 - Evaluation, observability, System Quality dashboard

### Evaluation harness

| Item | Location |
|---|---|
| Corpus (71 cases, 8 categories) | `backend/app/evaluation/cases.py` |
| Runner and metrics | `backend/app/evaluation/runner.py` |
| Adversarial composers | `backend/app/evaluation/adversarial.py` |
| Artifact store | `backend/app/evaluation/artifacts.py` |
| CLI | `scripts/run_evals.py` (`make eval`) |
| Output | `artifacts/evals/<run>.json`, `artifacts/evals/latest.json` |

Categories: concept resolution (13), safety (11), equipment (7), explicit
exclusions (6), longitudinal (10), adjustment (8), workout validation (8),
Copilot/MCP (8).

Current measured result: **71/71 passed, 0 unsafe escapes, 12/12 invariants
proven**, p50 14 ms / p95 225 ms per case.

Exit code is 0 only when every case passes and no unsafe exercise survives
final validation.

### Observability

| Item | Location |
|---|---|
| Trace contracts | `backend/app/domain/trace.py` |
| Post-hoc collector + call counter | `backend/app/observability/collector.py` |
| Bounded ring buffer (50) | `backend/app/observability/store.py` |
| Wiring | `app/api/routes.py`, `app/api/deps.py` |

Traces are built after a run from existing workflow state. No domain service
was modified to support tracing.

### Read-only API

```text
GET /api/system/evaluations/latest
GET /api/system/evaluations?limit=N
GET /api/system/evaluations/{run_id}
GET /api/system/traces?limit=N
GET /api/system/traces/{request_id}
```

`POST /api/system/evaluations/run` was **not** implemented. Triggering a
multi-second suite from an HTTP handler would need concurrency control, status
polling and a background runner, and the honest alternative - `make eval` - is
one command. The dashboard states that instead of hiding a button that shells
out.

### Dashboard

Route `frontend/app/system/page.tsx`. Components under
`frontend/components/system/`:

- `EvaluationOverview.tsx` - KPI cards, safety invariants, quality by category
- `EvaluationMatrix.tsx` - filterable case table + case detail
- `ExecutionTraces.tsx` - trace table, waterfall detail, MCP observability
- `EvaluationHistoryPanel.tsx` - recent runs and P95 trend

### Streaming

Scoped and deliberately skipped. See README *Known limitations* for the
reasoning: the workflow completes in ~50 ms with the offline stub, so a
progress stream would add transport and failure modes to narrate work that is
already finished.


---

## Phase 5 - Knowledge Graph Explorer

| Item | Location |
|---|---|
| Contracts + allowlists | `backend/app/domain/graph_explorer.py` |
| Shared traversal | `backend/app/graph/explorer.py` |
| Protocol additions | `backend/app/graph/repository.py` |
| In-memory backend | `backend/app/graph/memory_repository.py` |
| Neo4j backend (Cypher) | `backend/app/graph/neo4j_repository.py`, `queries.py` |
| Endpoints | `backend/app/api/routes.py` (`/api/graph/*`, GET only) |
| Route | `frontend/app/graph/page.tsx` |
| Components | `frontend/components/graph-explorer/` |
| Tests | `backend/tests/test_graph_explorer.py` (67), `frontend/tests/graph-explorer.test.tsx` (26) |

Visualization is a deterministic radial SVG layout in plain React. React Flow
was considered and declined: the layout is a pure function of the payload
(testable in jsdom), adds no dependency, and a stable ring explains connectivity
better than a force simulation that settles differently each render.

Deep links: `/graph?node=anatomy:knee` and
`/graph?mode=safety&exercise=<id>&name=<label>`, the latter linked from the
Safety & Provenance Inspector.
