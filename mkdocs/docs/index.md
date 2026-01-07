# canvas-ledger

A local, queryable ledger of Canvas LMS metadata for historical analysis.

## Why canvas-ledger?

Canvas LMS is effective for answering questions about the **current** state of a course. But it's poor at answering **historical** questions:

- What courses was I involved in three years ago, and in what capacity?
- When did a student drop a course, and what was their status before dropping?
- Who was the lead instructor for a co-taught course?
- How has a student's performance changed across semesters?

**canvas-ledger** gives instructors a durable, local, queryable historical record of Canvas metadata—independent of Canvas's retention policies, UI limitations, and API constraints.

## Key Features

- **Local-first**: Single SQLite database you own and control
- **Historical accuracy**: Tracks changes over time (adds, drops, grade changes)
- **Dual-truth model**: Preserves Canvas data exactly as reported, while allowing your annotations
- **CLI-first**: Scriptable, composable commands with JSON/CSV output
- **Incremental ingestion**: Safe to run repeatedly without duplicating data

## Quick Example

```bash
# Configure and initialize
cl config init
cl db migrate

# Ingest your Canvas courses
cl ingest catalog

# See your involvement timeline
cl query my-timeline

# Deep ingest a specific course
cl ingest offering 12345

# Query the roster
cl query offering 12345
```

## Getting Started

See the [Quickstart](quickstart.md) guide to get up and running.

## Documentation

- [Concepts](concepts.md) — Understand the dual-truth model and design principles
- [Data Model](data-model.md) — Database schema, file locations, and what gets tracked
- [Quickstart](quickstart.md) — Install, configure, and run your first queries
- [Workflows](workflows/semester-start.md) — Common usage patterns by time of semester
- [CLI Reference](cli/reference.md) — Complete command documentation
