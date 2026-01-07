# Mid-Semester Workflow

Catching enrollment changes during the add/drop period and beyond.

## Goals

- Capture enrollment changes (adds, drops, withdrawals)
- Update grade snapshots
- Track roster evolution

## When to Run

- After add/drop deadline
- After withdrawal deadline
- Before midterm grade submission
- Any time you need current data

## Steps

### 1. Re-Ingest Your Courses

```bash
# Re-ingest catalog to catch any new course assignments
uv run cl ingest catalog

# Re-ingest offerings you're tracking
uv run cl ingest offering 12345
```

The ingestion is idempotent—running it multiple times is safe and expected.

### 2. Check for Drift

After ingestion, see what changed:

```bash
# See enrollment changes for a course
uv run cl query drift offering 12345

# See changes for a specific student
uv run cl query drift person 67890
```

**Example output:**
```
Drift for Offering 12345
========================
2025-02-15 14:30:00
  Person 67890: enrollment_state changed from 'active' to 'deleted'
  Person 11111: NEW enrollment (StudentEnrollment, active)

2025-01-20 09:15:00
  Person 22222: current_score changed from 85.0 to 78.5
```

### 3. Review Ingestion Status

```bash
uv run cl ingest status
```

See summary of the last ingestion run, including drift counts.

## Understanding Drift

Drift detection tracks changes between ingestion runs:

| Change Type | What It Means |
|-------------|---------------|
| `enrollment_state: active → deleted` | Student dropped or was removed |
| `enrollment_state: active → completed` | Course concluded for this student |
| `NEW enrollment` | Student added after initial roster |
| `current_score` changed | Grade updated |
| `role` changed | Role modified (rare) |

## Grade Snapshots

Each ingestion captures current grade data. Over time, you build a history:

```bash
# See a person's grades with history
uv run cl query person 67890 --grades
```

This shows the most recent grades. Drift queries reveal how grades changed between ingestion runs.

## Tips

!!! tip "Regular Cadence"
    Consider a weekly or bi-weekly ingestion schedule during active semesters to maintain good drift granularity.

!!! warning "API Rate Limits"
    Deep ingestion makes many API calls. For courses with hundreds of students, expect ingestion to take a minute or two. Canvas rate limits are handled automatically.
