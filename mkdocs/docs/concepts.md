# Concepts

Understanding the core ideas behind canvas-ledger.

## The Problem with Canvas History

Canvas is a live system. It shows you the current state: who is enrolled *now*, what grades are *today*, what content exists *currently*. But instructors often need to answer historical questions:

- "What was my teaching load in 2022?"
- "When did this student drop, and what was their grade at that point?"
- "Who was listed as instructor across all my co-taught courses?"

Canvas doesn't preserve this history in an accessible way. Data changes, courses archive, and the past becomes murky.

## Observed vs. Declared Truth

canvas-ledger maintains two kinds of facts side-by-side:

### Observed Truth

Data exactly as reported by Canvas at the time of observation.

- **Never modified**: Once recorded, observed data is immutable
- **Timestamped**: Every observation records when it was seen
- **Non-destructive**: Even if data disappears from Canvas, your ledger retains it

Examples of observed truth:

- Course names, codes, and terms as Canvas reports them
- Enrollment states (active, dropped, completed)
- Grades at the time of ingestion
- Instructor assignments as Canvas lists them

### Declared Truth

Your corrections and annotations when Canvas doesn't reflect reality.

- **User-controlled**: You create, update, and delete these
- **Survives ingestion**: Re-running ingestion never overwrites your annotations
- **Coexists with observed data**: Both are shown in queries, clearly distinguished

Examples of declared truth:

- Lead instructor designation (when Canvas lists multiple instructors equally)
- Your involvement classification ("developed course", "guest lecturer")
- Course aliases (grouping renumbered courses together)

## Idempotent Ingestion

You can run ingestion at any time, repeatedly, without fear:

- **No duplicates**: Same data produces the same result
- **Drift detection**: Changes are detected and recorded
- **Safe re-runs**: Mid-semester, end of semester, historical backfill—all safe

This means you can:

1. Ingest at semester start to capture initial state
2. Re-ingest mid-semester to catch adds/drops
3. Re-ingest at semester end for final grades
4. Backfill historical semesters anytime

## Canonical Queries

canvas-ledger is designed to answer seven core questions:

| Query | Purpose |
|-------|---------|
| **Q1: My Timeline** | What courses have I been involved in, when, and in what capacity? |
| **Q2: Person History** | For a given person, what offerings were they in, and what role/state? |
| **Q3: Performance Summary** | For a given person, how did they do across offerings? |
| **Q4: Responsibility Clarity** | Who was lead instructor vs. other instructors? |
| **Q5: Roster Snapshot** | Who was enrolled in an offering, by section and role? |
| **Q6: Enrollment Drift** | What changed over time (adds, drops, state transitions)? |
| **Q7: Course Identity** | How to view history coherently across course renumbering? |

## Local, Inspectable, Durable

Your ledger is a single SQLite file:

- **Local**: No cloud dependencies (beyond Canvas API for ingestion)
- **Inspectable**: Open it with any SQLite tool
- **Portable**: Copy it, back it up, version control it
- **Durable**: Standard format that will be readable for decades

The default location is `~/.local/share/cl/ledger.db`, but you can configure any path.

## Schema Evolution

The database schema will change as canvas-ledger grows. Migrations are:

- **Forward-only**: No rollbacks needed
- **Automatic**: Run on first use after upgrade
- **Backed up**: Database copied before each migration

You don't need to think about migrations—they just work.
