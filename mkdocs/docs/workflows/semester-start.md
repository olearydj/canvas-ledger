# Semester Start Workflow

What to do at the beginning of each semester.

## Goals

- Capture initial course assignments
- Record your role declarations before the semester gets busy
- Establish baseline for drift detection

## Steps

### 1. Update Your Catalog

```bash
uv run cl ingest catalog
```

This picks up any new courses assigned to you for the upcoming term.

### 2. Deep Ingest Your Teaching Courses

For courses you're teaching (not just enrolled in), deep-ingest to capture the initial roster:

```bash
# Ingest each course you're teaching
uv run cl ingest offering 12345
uv run cl ingest offering 12346
```

!!! tip "Finding Course IDs"
    Course IDs appear in Canvas URLs: `https://canvas.edu/courses/12345`

    Or query your timeline and look at the output.

### 3. Declare Lead Instructor

For co-taught courses, record who is lead/grade-responsible:

```bash
# Mark yourself as lead instructor
uv run cl annotate lead 12345 YOUR_CANVAS_USER_ID
```

This annotation survives future ingestion runs and appears in queries alongside Canvas-reported instructor data.

### 4. Add Involvement Notes

Optionally classify your involvement:

```bash
uv run cl annotate involvement 12345 "Lead instructor, developed all materials"
uv run cl annotate involvement 12346 "Co-instructor, handled labs"
```

### 5. Verify Your Setup

```bash
# Check your timeline includes the new term
uv run cl query my-timeline --format json | jq '.[] | select(.term | contains("Spring 2025"))'

# Verify annotations are recorded
uv run cl annotate list
```

## What You've Accomplished

At semester start, your ledger now contains:

- All your course assignments for the new term
- Initial rosters for courses you're teaching
- Lead instructor declarations for co-taught courses
- Your involvement classifications

When you re-ingest mid-semester, the system will detect any changes (adds, drops, role changes) and record them as drift.
