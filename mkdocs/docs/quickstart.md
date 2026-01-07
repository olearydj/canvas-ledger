# Quickstart

Get canvas-ledger running in five minutes.

## Prerequisites

- Python 3.13+
- Access to Canvas LMS with an API token
- [uv](https://docs.astral.sh/uv/) for Python environment management

## Installation

```bash
# Clone the repository
git clone https://github.com/olearydj/canvas-ledger.git
cd canvas-ledger

# Install with uv
uv sync

# Verify installation
uv run cl --version
```

## Configuration

### Step 1: Get Your Canvas API Token

1. Log into Canvas
2. Go to Account → Settings
3. Scroll to "Approved Integrations"
4. Click "+ New Access Token"
5. Give it a name (e.g., "canvas-ledger") and generate
6. Copy the token (you won't see it again!)

### Step 2: Configure canvas-ledger

```bash
uv run cl config init
```

This will prompt you for:

- **Canvas URL**: Your institution's Canvas URL (e.g., `https://auburn.instructure.com`)
- **API Token**: The token you generated above

!!! tip "Token Storage"
    The token is stored securely—not in the config file. canvas-ledger supports environment variables (`CANVAS_API_TOKEN`) or 1Password integration.

### Step 3: Initialize the Database

```bash
uv run cl db migrate
```

This creates the SQLite database with all required tables.

## Your First Ingestion

### Ingest Your Course Catalog

```bash
uv run cl ingest catalog
```

This retrieves all courses visible to you in Canvas (any role: instructor, TA, student, etc.) and stores them locally.

**Example output:**
```
Ingesting catalog from Canvas...
Retrieved 274 courses
New: 274 | Updated: 0 | Unchanged: 0
Catalog ingestion complete.
```

### Query Your Timeline

```bash
uv run cl query my-timeline
```

See every course you've been involved in, with terms and roles.

**Example output:**
```
My Involvement Timeline
=======================

Fall 2024
  COMP 1234 - Introduction to Computing
    Role: TeacherEnrollment | State: active

Spring 2024
  COMP 5678 - Advanced Topics
    Role: TeacherEnrollment | State: completed
  ...
```

### Export as JSON

```bash
uv run cl query my-timeline --format json
```

Pipe to `jq`, save to file, or process programmatically.

## Deep Ingestion

For detailed roster and enrollment data, deep-ingest specific offerings:

```bash
# Get the Canvas course ID from your timeline or Canvas URL
uv run cl ingest offering 12345
```

This fetches:

- All sections in the course
- All enrollments (students, TAs, instructors)
- Grade data (current and final)
- Person details for each enrollee

Now you can query rosters:

```bash
# See who was enrolled
uv run cl query offering 12345

# See instructor assignments
uv run cl query offering 12345 --instructors

# Query a specific person's history
uv run cl query person 67890
```

## Adding Annotations

When Canvas doesn't reflect reality, add your own truth:

```bash
# Mark yourself as lead instructor
uv run cl annotate lead 12345 11111

# Add your involvement classification
uv run cl annotate involvement 12345 "Developed course materials"

# See your annotations
uv run cl annotate list
```

## Next Steps

- Read [Concepts](concepts.md) to understand the dual-truth model
- See [Workflows](workflows/semester-start.md) for seasonal usage patterns
- Explore the [CLI Reference](cli/reference.md) for all commands
