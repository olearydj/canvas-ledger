# canvas-ledger (cl)

A local, queryable ledger of Canvas LMS metadata. Maintains a durable historical record of your Canvas involvement for answering questions that Canvas cannot easily answer.

## Features

- **Local ledger**: All data stored locally in SQLite - no cloud dependencies after ingestion
- **Historical tracking**: Track enrollment changes over time with drift detection
- **Dual truth model**: Observed Canvas data + declared annotations (lead instructor, involvement classifications)
- **Course aliasing**: Group related offerings across course renumbering or special topics
- **Flexible output**: JSON, CSV, and table formats for all queries

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for package management
- Canvas API token (with appropriate permissions)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/canvas-ledger.git
cd canvas-ledger

# Install dependencies with uv
uv sync
```

## Quickstart

### 1. Initialize Configuration

```bash
uv run cl config init --canvas-url https://canvas.yourschool.edu
```

You'll be prompted for your Canvas base URL if not provided.

### 2. Set Your Canvas API Token

Get a Canvas API token from your Canvas account settings (Profile → Settings → Approved Integrations → New Access Token).

```bash
# Set as environment variable
export CANVAS_API_TOKEN='your-token-here'
```

Or use 1Password integration:

```bash
uv run cl config set secret_provider 1password
uv run cl config set op_reference "op://Vault/Canvas/credential"
```

### 3. Initialize the Database

```bash
uv run cl db migrate
```

### 4. Ingest Your Courses

```bash
# Fetch all courses visible to you
uv run cl ingest catalog

# Deep ingest a specific course (sections, enrollments, people)
uv run cl ingest offering 12345
```

### 5. Query Your Data

```bash
# See your involvement timeline
uv run cl query my-timeline

# Query a specific offering
uv run cl query offering 12345 --roster

# Query a person's enrollment history
uv run cl query person 67890

# Export as JSON or CSV
uv run cl query my-timeline --format json
uv run cl export offerings --format csv
```

## Core Commands

### Configuration

```bash
cl config init          # Initialize configuration
cl config show          # Display current settings
cl config set KEY VALUE # Update a setting
```

### Database

```bash
cl db migrate           # Run pending migrations
cl db status            # Show database and migration status
```

### Ingestion

```bash
cl ingest catalog           # Ingest all visible courses
cl ingest offering <id>     # Deep ingest a specific course
cl ingest status            # Show last ingestion details
```

### Queries

```bash
cl query my-timeline              # Your involvement timeline (Q1)
cl query person <id>              # Person enrollment history (Q2)
cl query person <id> --grades     # Person performance summary (Q3)
cl query offering <id> --instructors  # Instructor responsibility (Q4)
cl query offering <id> --roster   # Offering roster by section (Q5)
cl query drift person <id>        # Enrollment changes over time (Q6)
cl query alias <name>             # Query by course alias (Q7)
```

### Annotations

```bash
cl annotate lead <offering_id> <person_id>     # Declare lead instructor
cl annotate involvement <offering_id> "role"   # Classify your involvement
cl annotate alias create "Name" [offering_ids] # Create course alias
cl annotate alias add "Name" <offering_id>     # Add offering to alias
cl annotate list                               # List all annotations
```

### Export

```bash
cl export offerings [--format json|csv]        # Export all offerings
cl export enrollments <id> [--format json|csv] # Export course roster
cl export person <id> [--format json|csv]      # Export person history
```

## Global Options

```bash
-V, --version   # Show version
-v, --verbose   # Enable debug output
--help          # Show help for any command
```

## Data Model

canvas-ledger maintains two types of truth:

1. **Observed truth**: Data exactly as reported by Canvas
   - Offerings, terms, sections, people, enrollments
   - Timestamped with observation time
   - Historical states preserved (never deleted)

2. **Declared truth**: Your annotations
   - Lead/grade-responsible instructor designations
   - Involvement classifications
   - Course aliases for grouping related offerings

Queries return both observed and declared data, clearly distinguished.

## Architecture

```
src/cl/
├── cli/          # Typer CLI commands
├── canvas/       # Canvas API client (read-only)
├── ledger/       # Core persistence and queries
├── annotations/  # Declared truth management
├── export/       # JSON/CSV formatters
├── config/       # Configuration and secrets
└── migrations/   # Alembic database migrations
```

## Development

```bash
# Run tests
uv run pytest

# Run with verbose output
uv run cl -v ingest catalog
```

## License

MIT
