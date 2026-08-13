# Future's AI Engineering Take-Home: Knowledge-Graph Backed Coach Dashboard

**Time:** 1 day · **Stack:** your choice (justify it) · **Data:** synthetic only — never use real member data

This is a **full-stack + AI** project with two things at its core: designing an **effective, multi-agent workflow**, and **an architectural exercise in how to design and build an effective knowledge graph**. We care as much about that reasoning as about the running app.

Build a coach-facing dashboard that **generates safe, highly personalized workouts** and lets a coach **retrieve member context through an AI copilot**. Remember, to make a personalized workout, you should think about where various users might be with our product in terms of their journey & how various longitudinal data types might need to be considered differently.

**The core constraint:** recommendations are driven by a knowledge graph, not by the language model alone. The system resolves a coach's request onto canonical graph concepts — anatomy, equipment, injuries, etc. — and uses the graph's structure to make safe, auditable decisions. Safety constraints must be enforced **deterministically through graph traversal**, not left to a probabilistic prompt instruction.

---

## Why this matters

Coaches spend too much time manually piecing together a member's context — workouts, injuries, goals, adherence, chats, biomarkers, etc. — before they can give good advice. We want a system that does that grounding for them: faster workout generation, hyper-personalization at scale, injury-aware safety, and recommendations that can be **explained and audited**.

---

## What you'll build — one dashboard, two surfaces

### A · Workout Generator

To generate workouts, the coach must input a **prompt** (e.g. *"full-body exercise with isolation around my pecs"*, *"lower-body exercises that avoid aggravating a knee injury"*, etc.) and a **time window**. Your solution must collect these inputs, then call an **agentic workflow runtime** and render a structured workout in the browser (warmup / main / cooldown, with sets, reps, and rest).

It must support **interactive adjustment** driven by the graph:

| Coach says | Expected behavior |
|------------|-------------------|
| "Exclude deadlifts" | No deadlift variations appear |
| "Her left knee is bothering her" | Exclude / down-rank exercises that stress the knee (via the anatomy hierarchy, so sub-structures count too) |
| "She has no barbell, only dumbbells and a kettlebell" | Drop barbell-only exercises and **find equivalent alternatives** |

Every generated plan ships with a short **provenance trace**: why each exercise was chosen, which graph path justified it, and what was filtered out for safety.

### B · Coach AI Copilot

A chat panel with **retrieval over the member's context**. A coach logs in to a member in the morning and works their brief — for example: *congratulate the member on yesterday's workout*, then *check whether they're at risk of churning*.

It should support a **quick-prompt palette** and **charts**, e.g.:

- **For this member:** `Show me the brief` · `How's adherence trending?` · `Sleep this week` · `What changed since last week?`
- **Charts:** `Plot adherence trend` · `Show message pattern` · `Compare last 4 weeks`

The coach can see **past chat history and images**, ask follow-up questions, and get answers grounded in the member's actual data (not invented).

---

## The two knowledge graphs

### KG 1 · Movement / Clinical Domain graph

Human body movement and the exercise catalog, **grounded in published ontologies**.

- **Nodes:** exercises, muscles, joints / body regions, movement patterns, equipment, injuries / conditions.
- **Edges:** `targets` (muscle), `stresses` (joint/region), `requires` (equipment), `part-of` (anatomy hierarchy — so "knee" also covers its sub-structures), `contraindicated-for` (injury → unsafe movements).
- Map the catalog's taxonomy (the dataset has **19 muscle groups, 9 joints, 36 movement patterns, 32 equipment types**) onto ontology concepts with **SKOS** mappings, and record **why each exercise was selected** with **PROV-O** provenance.

### KG 2 · Member Context graph

The member's world, seeded from `data/member-context.json`: profile, goals, preferences, injuries, **coach↔member chat history**, **biomarkers** (resting HR, HRV, sleep), **lab results** (blood panel + DEXA scan), workout history, adherence, and churn signals. This is what the copilot retrieves over.

---

## Build steps

1. **Model & build the Movement/Clinical KG** with ontology grounding. Document the schema — node types, edge types, and what each means.
2. **Build the Member Context KG** by ingesting the provided synthetic member.
3. **Concept resolution** — map free text → canonical graph concepts (`"knee"` → the Knee joint node, `"kettlebell"` → the Kettlebell equipment node, `"bad lower back"` → a lumbar region node). A **3-pass resolver** is encouraged: **exact → fuzzy → embedding/vector fallback**, with **explicit confidence thresholds** and graceful degradation when nothing matches.
4. **Safety reasoning via graph traversal** — filter or down-rank the catalog by walking edges: injured joint (through `part-of`), available equipment, explicit exclusions, and preferences. The safety decision must be a **graph traversal**, not a sentence in the prompt.
5. **Agentic workout-generation runtime** — turn the form (prompt + time) into a structured plan plus the **provenance trace**.
6. **Coach AI Copilot** — retrieval over the Member Context KG: answer member-specific questions, run the quick prompts, render the charts, and surface the morning brief and churn risk.
7. **Dashboard UI** — coach login (mock auth is fine), a member view, the generator panel and the copilot panel, chart rendering, and chat with history/images.
8. **Tests** — at minimum the **concept resolver** and the **safety filter**. Pick the critical paths and explain why you chose them.
9. **Comprehensive README** — see *Deliverable*.

---

## Ontologies & resources

Ground the domain graph in real ontologies. A **small, well-justified subset used meaningfully** beats wiring up everything shallowly.

| Ontology | Use it for | Link |
|----------|-----------|------|
| **OPE** — Ontology of Physical Exercises | Exercises, musculoskeletal systems, equipment, injuries | https://bioportal.bioontology.org/ontologies/OPE |
| **COPPER** — COntextualised & Personalised Physical activity and Exercise Recommendations Ontology | Personalization / behaviour-change concepts | https://bioportal.bioontology.org/ontologies/COPPER |
| **SNOMED CT** (via NCI EVS) | Clinical anatomy, joints, injuries / conditions | Browser: https://evsexplore.semantics.cancer.gov/evsexplore/concept/snomedct_us/&lt;code&gt; · API: `https://api-evsrest.nci.nih.gov/` → `GET /api/v1/concept/snomedct_us/<code>` (terminology `snomedct_us`) |
| **PROV-O** — W3C Provenance Ontology | Provenance — why a recommendation was made | https://www.w3.org/TR/prov-o/ |
| **SKOS** — Simple Knowledge Organization System | Concept mapping (catalog/free-text terms ↔ ontology concepts) | https://www.w3.org/TR/skos-reference/ |

**This is also a research exercise.** We don't expect you to ingest these ontologies wholesale — part of the task is deciding what to actually use. We want to see your reasoning on:

- **What to pull** from each ontology, and **what to leave out**.
- **Why** those concepts/relationships matter for safe, personalized recommendations.
- **How to store it** — graph store choice, schema, how ontology concepts map onto the catalog (a clean hand-rolled ontology aligned to these concepts is perfectly acceptable; you do not have to parse full OWL).
- **How to build the knowledge graph** — ingestion approach, concept mapping, and how the two graphs relate.

Document the **decisions and trade-offs** you made, and include the **architecture diagram** — these are required, not optional.

---

## Provided data

Everything is in [`data/`](./data) and is **synthetic** — clearly fictional, no real person or PHI.

- **[`data/exercises.json`](./data/exercises.json)** — 50 exercises. Key fields: `muscle_groups`, `joints_loaded`, `movement_patterns`, `equipment_required`, `priority_tier`, `is_bilateral`, `bilateral_pair_id`.
- **[`data/member-context.json`](./data/member-context.json)** — one rich sample member (Jordan Rivera): `profile`, `goals`, `preferences`, `equipment_available`, `injuries`, `workout_history`, `adherence`, `biomarkers`, `labs` (blood panel + DEXA), `chat_history`, and a `coach_brief` with morning tasks + churn risk. It is intentionally set up for the scenarios above — a recovering **left-knee** injury, **no barbell** at home, a **declining adherence** trend, and a workout to celebrate.

**Generate any additional data yourself, synthetically. Never use real member or personal data.**

---

## What we're evaluating

- **Graph & ontology modeling** — edge semantics; is the graph doing real work, or is it semantic search with extra steps?
- **Concept resolution** — quality on messy input, and graceful degradation when nothing matches.
- **Safety from traversal** — injury/equipment constraints that actually come from the graph, not the prompt.
- **Full-stack product thinking** — does the dashboard help a coach do their job?
- **System design & API** — clean boundaries, typed contracts, sane data flow.
- **Developer experience** — does it run with one command? Is the README clear?
- **Communication** — how you articulate trade-offs and decisions.
- **Working in ambiguity** — where the spec is open, make a decision and explain it.

**Performance:** aim for AI responses under ~5s and be reasonable about token efficiency. We care more about *how you reason* about these than about hitting an exact number.

---

## Nice-to-haves

- Graph visualization
- Multi-agent orchestration
- Streaming responses
- An evaluation pipeline (retrieval relevance, recommendation quality)
- Observability / tracing of LLM calls, tools, and graph queries
- Deeper SNOMED grounding
- Longitudinal reasoning (progression and adherence over time)

---

## Deliverable

A runnable **GitHub repo** with a **comprehensive README** — written as a **staff engineer** would, to defend the work in review:

- **High-level system architecture diagram** — the major components and how data flows (dashboard → agentic runtime → knowledge graph(s) → LLM/vector store). A simple diagram (Mermaid, Excalidraw, hand-drawn photo) is fine.
- **Architecture & tech choices** — what you used and **why** (defend the stack).
- **How to run locally** — ideally one command.
- **How you used AI** to build this project.
- **Challenges, trade-offs, and technical decisions** — articulated explicitly.
- **How you'd evaluate this system in production** — metrics, failure modes, safety monitoring.
- **2–3 example inputs** with their generated plans — include **one injury case** and **one limited-equipment case** — showing the plan and the provenance/filtering trace.

When you're done, share the repo link. If anything in the spec is ambiguous, make a reasonable decision and document it — that reasoning is part of what we're assessing.
