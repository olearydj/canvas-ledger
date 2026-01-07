# Retrospective Workflow

Using your ledger for annual reviews, teaching portfolios, and historical analysis.

## Goals

- Answer questions about past teaching
- Generate data for annual reviews
- Support letters of recommendation
- Analyze teaching patterns over time

## Common Queries

### Teaching History Report

```bash
# Full timeline as JSON for processing
uv run cl query my-timeline --format json > teaching-history.json

# Filter to a specific term
uv run cl query my-timeline --format json | jq '.[] | select(.term | contains("2024"))'
```

### Student Lookup

When writing a letter of recommendation:

```bash
# Find all courses where a student was enrolled
uv run cl query person 67890

# Include their grades
uv run cl query person 67890 --grades
```

**Example output:**
```
Person History: Jane Student (67890)
====================================

Fall 2024 - COMP 1234: Introduction to Computing
  Section: Section 001
  Role: StudentEnrollment
  State: completed
  Final Grade: A

Spring 2024 - COMP 2345: Data Structures
  Section: Section 002
  Role: StudentEnrollment
  State: completed
  Final Grade: A-
```

### Course Rosters

For historical course records:

```bash
# Get the final roster for a past course
uv run cl query offering 12345 --format csv > roster-fall-2024.csv
```

### Lead Instructor Verification

For tenure/promotion documentation:

```bash
# See all offerings where you declared lead instructor
uv run cl annotate list | grep "lead"

# Query specific offering responsibility
uv run cl query offering 12345 --instructors
```

## Backfilling Historical Data

If you're just starting with canvas-ledger, you can backfill:

```bash
# Ingest catalog to get all visible courses (including past terms)
uv run cl ingest catalog

# Deep ingest important historical courses
uv run cl ingest offering 11111  # Fall 2023 course
uv run cl ingest offering 22222  # Spring 2023 course
```

!!! note "Historical Limitations"
    Canvas may not retain full enrollment history for very old courses. You'll capture what's still available.

## Course Aliasing

For courses that have been renumbered:

```bash
# Create an alias for a course that was renumbered
uv run cl annotate alias create "intro-computing" 12345 23456 34567

# Query across all versions
uv run cl query alias "intro-computing"
```

This groups COMP 1000 (old number), COMP 1100 (renumbered), and COMP 1200 (renumbered again) under one logical identity.

## Export for External Use

```bash
# Export offerings for spreadsheet analysis
uv run cl export offerings --format csv > all-offerings.csv

# Export a course roster
uv run cl export enrollments 12345 --format csv > roster.csv

# Export person history
uv run cl export person 67890 --format json > student-record.json
```

## Data Integrity

Your ledger is a durable historical record:

- **Observed data is never deleted**: Even if Canvas removes a course
- **Annotations persist**: Your declarations survive any re-ingestion
- **Timestamps preserved**: Know exactly when each observation was made

Back up your database file (`~/.local/share/cl/ledger.db`) periodically for additional safety.
