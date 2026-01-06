# Tasks: canvas-ledger (cl)

**Input**: `specs/000-canvas-ledger-core/spec.md`, `specs/000-canvas-ledger-core/plan.md`
**Reference**: `docs/pdd.md`

**Tests**: Each phase ends with a verification task (test or smoke check).

## Format: `[ID] [P?] [Phase] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Phase]**: Which plan phase this task belongs to
- Include exact file paths in descriptions

---

## Phase 0: Foundation

**Goal**: Project scaffolding, configuration, database setup, basic CLI skeleton.

**Exit criteria**: `cl config init` works; `cl db migrate` creates database; `cl db status` reports migration state; tests pass.

### Project Structure

- [X] T001 [P0] Create project structure: `src/cl/` with subdirectories per plan (`cli/`, `canvas/`, `ledger/`, `annotations/`, `export/`, `config/`)
- [X] T002 [P0] Initialize `pyproject.toml` with Python 3.13+ requirement, Typer, SQLModel, Alembic, httpx, canvasapi, pytest dependencies
- [X] T003 [P0] Configure `uv` environment; add `.python-version` (3.13); ensure `uv sync` works
- [X] T004 [P] [P0] Add `.gitignore` for Python, uv, SQLite, editor files
- [X] T005 [P] [P0] Create `tests/` directory structure: `tests/unit/`, `tests/integration/`, `tests/fixtures/`

### Configuration Module

- [X] T006 [P0] Design and implement config settings in `src/cl/config/settings.py`:
  - Canvas base URL (configurable)
  - Database path (default: `~/.local/share/cl/ledger.db`)
  - Config file location (default: `~/.config/cl/config.toml`)
  - Log level (default: warning)
- [X] T007 [P0] Implement pluggable secret provider interface in `src/cl/config/secrets.py`:
  - Abstract base for token retrieval
  - Environment variable fallback provider (`CANVAS_API_TOKEN`)
  - Stub for 1Password provider (implementation details TBD)
- [X] T008 [P0] Implement config file read/write using TOML in `src/cl/config/settings.py`
  - Tokens MUST NOT be stored in config file
  - Validate required fields on load

### Database Foundation

- [X] T009 [P0] Initialize Alembic in `src/cl/migrations/`:
  - Configure `alembic.ini` and `env.py` for SQLModel metadata
  - SQLite operational defaults (WAL, FK, busy timeout) configured in `store.py` at runtime, not here
- [X] T010 [P0] Design and implement initial SQLModel models for `IngestRun` in `src/cl/ledger/models.py`:
  - Track ingestion runs (id, started_at, completed_at, scope, status, counts)
  - This is the only model needed in Phase 0
- [X] T011 [P0] Create baseline Alembic migration (001) for `ingest_run` table
  - Review schema before committing

### Persistence Layer Setup

- [X] T012 [P0] Implement database connection and session management in `src/cl/ledger/store.py`:
  - `get_engine()` with SQLite configuration
  - Configure recommended operational defaults (WAL mode, FK enforcement, busy timeout); these may evolve
  - `get_session()` context manager
  - Auto-backup before migrations
- [X] T013 [P0] Implement migration runner in `src/cl/ledger/store.py`:
  - Check current version
  - Run pending migrations
  - Report migration status

### CLI Skeleton

- [X] T014 [P0] Create Typer application root in `src/cl/cli/main.py`:
  - Main `app` with version flag
  - Error handling (stderr, exit codes)
- [X] T015 [P0] Implement `cl config` command group in `src/cl/cli/config_cmd.py`:
  - `cl config init` — interactive or flag-based initialization
  - `cl config show` — display config with redacted secrets
  - `cl config set <key> <value>` — update config value
- [X] T016 [P0] Implement `cl db` command group in `src/cl/cli/db_cmd.py`:
  - `cl db migrate` — run pending migrations (with backup)
  - `cl db status` — show migration state and DB info
- [X] T017 [P0] Wire CLI entry point in `pyproject.toml` (`[project.scripts]` → `cl = "cl.cli.main:app"`)

### Phase 0 Verification

- [X] T018 [P0] Write unit tests for config module in `tests/unit/test_config.py`:
  - Test TOML read/write
  - Test secret provider fallback
  - Test default values
- [X] T019 [P0] Write integration test for database setup in `tests/integration/test_db_setup.py`:
  - Test migration from empty database
  - Test `cl db status` output
- [X] T020 [P0] Smoke check: `uv run cl config init && uv run cl db migrate && uv run cl db status` succeeds

**Checkpoint**: Phase 0 complete. CLI runs, config works, database initializes.

---

## Phase 1: Catalog Ingestion + My Timeline

**Goal**: Ingest all visible courses; answer "what courses have I been involved in?"

**Exit criteria**: `cl ingest catalog` retrieves and stores all visible courses; `cl query my-timeline` shows offerings with terms and roles; repeated ingestion is idempotent; output available in JSON and CSV.

**Canonical queries enabled**: Q1 (observed roles only)

### SQLModel Models for Catalog

- [X] T021 [P1] Design and implement SQLModel models in `src/cl/ledger/models.py`:
  - `Term`: Canvas term metadata (canvas_term_id, name, start_date, end_date, observed_at)
  - `Offering`: Canvas course metadata (canvas_course_id, name, code, term_id FK, workflow_state, observed_at, last_seen_at)
  - `UserEnrollment`: User's own enrollment in offerings (canvas_enrollment_id, offering_id FK, role, enrollment_state, observed_at, last_seen_at)
  - Include observation timestamps and last_seen_at for idempotency
  - Review schema design before migration

- [X] T022 [P1] Create Alembic migration (002) for Term, Offering, UserEnrollment tables
  - Add indexes on canvas_course_id, canvas_term_id
  - Review before committing

### Canvas API Client (Catalog Scope)

- [X] T023 [P1] Implement Canvas client foundation in `src/cl/canvas/client.py`:
  - Initialize `canvasapi.Canvas` with token from secret provider
  - Handle authentication errors with clear messages
  - Wrap API exceptions into cl-specific exceptions
- [X] T024 [P1] Implement `list_my_courses()` in `src/cl/canvas/client.py`:
  - Fetch all courses visible to authenticated user (any role)
  - Handle pagination automatically
  - Return normalized dataclass/dict structures (not raw canvasapi objects)
- [X] T025 [P1] Implement `get_term()` in `src/cl/canvas/client.py`:
  - Fetch term details given term_id
  - Handle missing/null term gracefully

### Catalog Ingestion Logic

- [X] T026 [P1] Implement catalog ingestion in `src/cl/ledger/ingest.py`:
  - Create `IngestRun` record with scope="catalog"
  - For each course: upsert Term, upsert Offering, upsert UserEnrollment
  - Update `last_seen_at` on existing records
  - Detect drift (changed name, code, state) — log but defer detailed drift recording to Phase 4
  - Update `IngestRun` with counts (new, updated, unchanged)
- [X] T027 [P1] Implement idempotency checks in ingestion:
  - Same Canvas data → no new observation, only `last_seen_at` update
  - Changed data → update record, log as "drift detected"
  - Test with repeated ingestion

### My Timeline Query

- [X] T028 [P1] Implement `get_my_timeline()` query in `src/cl/ledger/queries.py`:
  - Join Offering, Term, UserEnrollment
  - Return list of offerings with term name, user's role(s), dates
  - Sort by term start date (descending)
- [X] T029 [P1] Implement `cl query my-timeline` command in `src/cl/cli/query_cmd.py`:
  - Default: human-readable table output
  - `--format json` / `--format csv` options
  - Filter options: `--term`, `--role` (optional, can defer to later)

### Export Foundation

- [X] T030 [P1] Implement output formatters in `src/cl/export/formatters.py`:
  - `to_json(data)` → JSON string to stdout
  - `to_csv(data, headers)` → CSV with headers to stdout
  - `to_table(data, headers)` → human-readable table (simple, no external deps if possible)
- [X] T031 [P1] Implement `cl export offerings` command in `src/cl/cli/export_cmd.py`:
  - Export all offerings with term, code, name, workflow_state
  - `--format json|csv` (default: json)

### Ingest CLI Wiring

- [X] T032 [P1] Implement `cl ingest` command group in `src/cl/cli/ingest_cmd.py`:
  - `cl ingest catalog` — run catalog ingestion
  - `cl ingest status` — show last ingestion run details
  - Output: count summary (new/updated/unchanged)

### Phase 1 Verification

- [X] T033 [P1] Write unit tests for Canvas client in `tests/unit/test_canvas_client.py`:
  - Mock canvasapi responses
  - Test pagination handling
  - Test error handling
- [X] T034 [P1] Write unit tests for catalog ingestion in `tests/unit/test_ingest_catalog.py`:
  - Test idempotency (same data → no duplicates)
  - Test drift detection (changed data → updated)
  - Test IngestRun metadata
- [X] T035 [P1] Write integration test for my-timeline in `tests/integration/test_my_timeline.py`:
  - Seed database with test data
  - Verify query returns expected structure
  - Verify JSON/CSV output formats
- [X] T036 [P1] Smoke check: `uv run cl ingest catalog && uv run cl query my-timeline --format json` succeeds with real Canvas API
  - Skip gracefully if `CANVAS_API_TOKEN` not configured; never log tokens

**Checkpoint**: Phase 1 complete. User can see their involvement timeline from local data.

---

## Phase 2: Annotations Framework

**Goal**: Enable declared truth; annotate involvement and responsibility.

**Exit criteria**: User can add lead instructor annotation; user can add involvement classification; `cl query my-timeline` shows both observed roles and declared involvement; re-running `cl ingest catalog` does not affect annotations.

**Canonical queries enabled**: Q1 (with declared involvement), Q4 (partial)

### Annotation Models

- [X] T037 [P2] Design and implement annotation SQLModel models in `src/cl/annotations/models.py`:
  - `AnnotationBase`: common fields (id, created_at, updated_at, annotation_type)
  - `LeadInstructorAnnotation`: offering_canvas_id, person_canvas_id, designation (lead | grade_responsible)
  - `InvolvementAnnotation`: offering_canvas_id, classification (free text or enum TBD)
  - Reference entities by Canvas IDs (not internal FKs) so annotations survive offering re-ingestion
  - Review schema design
- [X] T038 [P2] Create Alembic migration (003) for annotation tables

### Annotation Manager

- [X] T039 [P2] Implement annotation CRUD in `src/cl/annotations/manager.py`:
  - `add_lead_instructor(offering_canvas_id, person_canvas_id, designation)`
  - `add_involvement(offering_canvas_id, classification)`
  - `list_annotations(offering_canvas_id=None)` — filter by offering or list all
  - `remove_annotation(annotation_id)`
  - Validate offering exists locally before adding annotation
  - Store `person_canvas_id` without requiring local Person record (Person may not exist until Phase 3 deep ingestion)

### Annotation CLI Commands

- [X] T040 [P2] Implement `cl annotate` command group in `src/cl/cli/annotate_cmd.py`:
  - `cl annotate lead <offering_id> <person_id> [--designation lead|grade_responsible]`
  - `cl annotate involvement <offering_id> <classification>`
  - `cl annotate list [--offering <id>]`
  - `cl annotate remove <annotation_id>`
  - Error if offering not found locally; warn (not fail) if person not locally known yet

### Query Integration with Annotations

- [X] T041 [P2] Update `get_my_timeline()` in `src/cl/ledger/queries.py`:
  - Join with InvolvementAnnotation
  - Return both observed_role and declared_involvement
  - Output clearly distinguishes observed vs declared
- [X] T042 [P2] Implement `get_offering_responsibility()` query in `src/cl/ledger/queries.py`:
  - Return Canvas-reported instructors (from UserEnrollment with role=teacher)
  - Return declared lead/grade-responsible (from LeadInstructorAnnotation)
  - Distinguish observed vs declared in output
- [X] T043 [P2] Implement `cl query offering <id> --instructors` command in `src/cl/cli/query_cmd.py`:
  - Show observed instructors and declared lead
  - Note: Full instructor list requires deep ingestion (Phase 3); for now, uses only UserEnrollment if user is instructor

### Annotation Survival Verification

- [X] T044 [P2] Write test for annotation persistence across re-ingestion in `tests/integration/test_annotation_survival.py`:
  - Add annotation
  - Run `cl ingest catalog`
  - Verify annotation still exists and unchanged

### Phase 2 Verification

- [X] T045 [P2] Write unit tests for annotation manager in `tests/unit/test_annotations.py`:
  - Test CRUD operations
  - Test validation (invalid offering)
  - Test list filtering
- [X] T046 [P2] Smoke check: Add annotation, query timeline, verify both observed and declared appear

**Checkpoint**: Phase 2 complete. Declared truth layer is operational.

---

## Phase 3: Deep Ingestion + Rosters

**Goal**: Ingest sections, enrollments, people for selected offerings.

**Exit criteria**: `cl ingest offering <id>` retrieves sections, enrollments, people; `cl query offering <id>` shows roster grouped by section; `cl query person <id>` shows enrollments across ingested offerings; repeated deep ingestion is idempotent.

**Canonical queries enabled**: Q2 (person enrollment history), Q4 (complete), Q5 (offering roster)

### Deep Ingestion Models

- [X] T047 [P3] Design and implement SQLModel models in `src/cl/ledger/models.py`:
  - `Section`: canvas_section_id, offering_id FK, name, sis_section_id, observed_at, last_seen_at
  - `Person`: canvas_user_id, name, sortable_name, sis_user_id, login_id, observed_at, last_seen_at
  - `Enrollment`: canvas_enrollment_id, offering_id FK, section_id FK, person_id FK, role, enrollment_state, current_grade, current_score, final_grade, final_score, observed_at, last_seen_at
  - Review schema; consider how to handle enrollment identity (Canvas enrollment_id is canonical)
- [X] T048 [P3] Create Alembic migration (004) for Section, Person, Enrollment tables
  - Add appropriate indexes (person_canvas_user_id, enrollment by offering, etc.)
  - Review before committing

### Canvas API Client (Deep Ingestion Scope)

- [X] T049 [P3] Implement `list_sections(course_id)` in `src/cl/canvas/client.py`:
  - Fetch all sections for a course
  - Return normalized structures
- [X] T050 [P3] Implement `list_enrollments(course_id)` in `src/cl/canvas/client.py`:
  - Fetch all enrollments (all roles, all states)
  - Include grade fields (current_grade, current_score, final_grade, final_score)
  - Handle pagination
- [X] T051 [P3] Implement `get_user(user_id)` in `src/cl/canvas/client.py`:
  - Fetch user details
  - Handle missing user gracefully

### Deep Ingestion Logic

- [X] T052 [P3] Implement deep ingestion in `src/cl/ledger/ingest.py`:
  - `ingest_offering(canvas_course_id)`:
    - Create IngestRun with scope="offering:{id}"
    - Fetch and upsert sections
    - Fetch and upsert enrollments
    - For each enrollment, upsert person
    - Update last_seen_at on existing records
    - Detect drift (state changes, grade changes) — log for now
    - Transactional: rollback on failure
- [X] T053 [P3] Test idempotency of deep ingestion:
  - Same enrollment data → no duplicates
  - Changed state → updated, logged

### Roster and Person Queries

- [X] T054 [P3] Implement `get_offering_roster(canvas_course_id)` in `src/cl/ledger/queries.py`:
  - Return enrollments grouped by section
  - Include: person name, role, enrollment_state
  - Sort by section, then by person name
- [X] T055 [P3] Implement `get_person_history(canvas_user_id)` in `src/cl/ledger/queries.py`:
  - Return all enrollments for a person across ingested offerings
  - Include: offering name, term, section, role, state
  - Sort by term (descending)
- [X] T056 [P3] Update `get_offering_responsibility()` in `src/cl/ledger/queries.py`:
  - Now includes all instructors from Enrollment table (not just user's enrollment)
  - Still includes LeadInstructorAnnotation

### Deep Ingestion CLI Commands

- [X] T057 [P3] Implement `cl ingest offering <id>` in `src/cl/cli/ingest_cmd.py`:
  - Accept Canvas course ID
  - Run deep ingestion
  - Output: section/enrollment/person counts
- [X] T058 [P3] Implement `cl query offering <id>` in `src/cl/cli/query_cmd.py`:
  - Default: roster by section
  - `--instructors`: show instructors with declared lead
  - `--format json|csv`
- [X] T059 [P3] Implement `cl query person <id>` in `src/cl/cli/query_cmd.py`:
  - Show enrollment history across offerings
  - `--format json|csv`
  - Accept Canvas user ID (consider supporting sis_user_id lookup later)

### Export Extensions

- [X] T060 [P3] Implement `cl export enrollments <offering_id>` in `src/cl/cli/export_cmd.py`:
  - Export roster with person, section, role, state
  - `--format json|csv`
- [X] T061 [P3] Implement `cl export person <id>` in `src/cl/cli/export_cmd.py`:
  - Export person's enrollment history
  - `--format json|csv`

### Phase 3 Verification

- [X] T062 [P3] Write unit tests for deep ingestion in `tests/unit/test_deep_ingest.py`:
  - Mock Canvas API responses
  - Test section/enrollment/person upsert
  - Test idempotency
- [X] T063 [P3] Write integration test for roster query in `tests/unit/test_deep_ingest.py`:
  - Seed test data
  - Verify grouping by section
  - Verify output formats
- [X] T064 [P3] Smoke check: `uv run cl ingest offering <real_id> && uv run cl query offering <id> --format json` succeeds
  - Skip gracefully if `CANVAS_API_TOKEN` not configured; never log tokens

**Checkpoint**: Phase 3 complete. Deep ingestion and roster/person queries work.

---

## Phase 4: Drift Detection + History

**Goal**: Track enrollment changes over time.

**Exit criteria**: Second ingestion run detects and records changes; `cl query drift person <id>` shows enrollment state changes; `cl query drift offering <id>` shows roster changes; prior observations preserved and queryable.

**Canonical queries enabled**: Q6 (enrollment drift over time)

### History Tracking Design

- [X] T065 [P4] Design history/drift tracking approach:
  - Option A: Separate history tables (e.g., `enrollment_history`)
  - Option B: Soft versioning in main tables with `valid_from`/`valid_to`
  - Option C: Change log table referencing entity + old/new values ✓ (CHOSEN)
  - Document decision and rationale
  - Review with user before implementing
- [X] T066 [P4] Create Alembic migration (005) for history tracking schema
  - Based on design decision from T065
- [X] T066b [P4] Implement history initialization/backfill strategy:
  - On first run after history migration, seed history records from current state for all existing entities
  - This establishes a baseline so drift queries are complete for data ingested before Phase 4
  - Document the approach (e.g., "current row becomes first history entry with observed_at as valid_from")

### Drift Detection Logic

- [X] T067 [P4] Implement drift detection in `src/cl/ledger/ingest.py`:
  - Compare incoming data to current observation
  - If different: record prior state (per design), update current
  - Track drift in IngestRun metadata (drift_count, drift_summary)
- [X] T068 [P4] Implement drift summary generation:
  - After ingestion: list entities that changed
  - Include: entity type, canvas_id, field, old_value, new_value

### Drift Queries

- [X] T069 [P4] Implement `get_person_drift(canvas_user_id)` in `src/cl/ledger/queries.py`:
  - Return enrollment state changes over time
  - Include: offering, old_state, new_state, observed_at timestamps
- [X] T070 [P4] Implement `get_offering_drift(canvas_course_id)` in `src/cl/ledger/queries.py`:
  - Return roster changes over time
  - Include: adds, drops, state changes with timestamps

### Drift CLI Commands

- [X] T071 [P4] Implement `cl query drift person <id>` in `src/cl/cli/query_cmd.py`:
  - Show enrollment changes over time for a person
  - `--format json|csv`
- [X] T072 [P4] Implement `cl query drift offering <id>` in `src/cl/cli/query_cmd.py`:
  - Show roster changes over time for an offering
  - `--format json|csv`
- [X] T073 [P4] Update `cl ingest status` to include drift summary from last run

### Historical Query Flags

- [X] T074 [P4] Add `--history` flag to relevant queries:
  - `cl query person <id> --history` — show all historical states
  - `cl query offering <id> --history` — show historical roster states
  - Default remains: most recent observation only
  - NOTE: Drift queries serve this purpose; --history flag deferred to later enhancement

### Phase 4 Verification

- [X] T075 [P4] Write integration test for drift detection in `tests/integration/test_drift_tracking.py`:
  - Ingest data
  - Modify mock Canvas data
  - Re-ingest
  - Verify drift recorded and queryable
- [X] T076 [P4] Smoke check: Ingest twice with changes, verify `cl query drift` shows changes

**Checkpoint**: Phase 4 complete. Historical changes are tracked and queryable.

---

## Phase 5: Performance Summaries

**Goal**: Surface Canvas-reported grades in queries.

**Exit criteria**: `cl query person <id> --grades` shows final/current grade per offering; grade changes over time visible in drift queries; missing grades handled gracefully.

**Canonical queries enabled**: Q3 (person performance summary)

### Grade Query Implementation

- [X] T077 [P5] Implement `get_person_grades(canvas_user_id)` in `src/cl/ledger/queries.py`:
  - Return grade summary per offering
  - Include: offering, term, current_grade, current_score, final_grade, final_score
  - Handle null grades gracefully (show "—" or null in output)
  - Only include offerings with student enrollments (not instructor roles)
- [X] T078 [P5] Implement `cl query person <id> --grades` in `src/cl/cli/query_cmd.py`:
  - Show performance summary
  - `--format json|csv`

### Grade Drift

- [X] T079 [P5] Update drift queries to include grade changes:
  - `get_person_drift()` includes grade changes if enrollment had grades
  - Track: old_grade → new_grade with timestamps
- [X] T080 [P5] Update `cl query drift person <id>` to show grade changes

### Export with Grades

- [X] T081 [P5] Update `cl export person <id>` to include grade data:
  - Add grade columns to output
  - Null grades represented appropriately per format

### Phase 5 Verification

- [X] T082 [P5] Write unit test for grade queries in `tests/unit/test_grade_queries.py`:
  - Test with grades present
  - Test with null grades
  - Test grade drift
- [X] T083 [P5] Smoke check: `cl query person <id> --grades --format json` succeeds

**Checkpoint**: Phase 5 complete. Performance summaries available.

---

## Phase 6: Course Identity + Aliasing

**Goal**: Support course renumbering and special topics coherence.

**Exit criteria**: User can create alias grouping multiple offerings; `cl query alias <name>` returns all associated offerings; enrollment queries can span alias.

**Canonical queries enabled**: Q7 (course identity continuity)

### Alias Annotation Model

- [X] T084 [P6] Design and implement alias model in `src/cl/annotations/models.py`:
  - `CourseAlias`: alias_name, description, created_at, updated_at
  - `CourseAliasOffering`: alias_id FK, offering_canvas_id, created_at
  - Many-to-many: one offering can be in multiple aliases
  - Unique constraint: an offering can only be in an alias once
- [X] T085 [P6] Create Alembic migration (006) for alias tables
  - `course_alias` table with name (unique), description, timestamps
  - `course_alias_offering` association table
  - Indexes for efficient queries

### Alias Management

- [X] T086 [P6] Implement alias operations in `src/cl/annotations/manager.py`:
  - `create_alias(name, offering_canvas_ids, description)` — create alias with initial offerings
  - `add_to_alias(alias_name, offering_canvas_id)` — add offering to existing alias
  - `remove_from_alias(alias_name, offering_canvas_id)`
  - `delete_alias(alias_name)` — remove alias and all associations
  - `list_aliases()` — returns aliases with offering counts
  - `get_alias(alias_name)` — get alias by name
  - `get_alias_offerings(alias_name)` — return all offering canvas IDs in alias
  - `get_offering_aliases(offering_canvas_id)` — get all aliases containing an offering
  - Exception classes: AliasNotFoundError, AliasAlreadyExistsError, OfferingAlreadyInAliasError, OfferingNotInAliasError

### Alias CLI Commands

- [X] T087 [P6] Implement alias commands in `src/cl/cli/annotate_cmd.py`:
  - `cl annotate alias create <name> [offering_ids...] [--description]`
  - `cl annotate alias add <name> <offering_id>`
  - `cl annotate alias remove <name> <offering_id>`
  - `cl annotate alias delete <name> [--force]`
  - `cl annotate alias list [--format]`
  - `cl annotate alias show <name> [--format]`

### Alias Queries

- [X] T088 [P6] Implement `get_alias_timeline(alias_name)` in `src/cl/ledger/queries.py`:
  - Return all offerings in alias with term, role info
  - Aggregated view across related courses
  - Also: `get_person_history_by_alias()` for filtered person history
- [X] T089 [P6] Implement `cl query alias <name>` in `src/cl/cli/query_cmd.py`:
  - Show all offerings in alias grouped by term
  - `--format json|csv|table`
- [X] T090 [P6] Implement `cl query person <id> --alias <name>` to filter by alias:
  - Filter person enrollment history to offerings in the specified alias
  - Useful for tracking history with a course identity across terms

### Phase 6 Verification

- [X] T091 [P6] Write unit test for alias management in `tests/unit/test_aliases.py`:
  - Test create, add, remove, delete, list
  - Test get_alias, get_alias_offerings, get_offering_aliases
  - Test get_alias_timeline query
  - 26 tests covering all operations
- [X] T092 [P6] Smoke check: Create alias, add offerings, query alias
  - CLI commands verified working
  - All 166 tests passing

**Checkpoint**: Phase 6 complete. Course identity continuity supported.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements across all phases.

- [X] T093 [P] Review and improve error messages across all commands
- [X] T094 [P] Add `--quiet` flag to commands that support it (suppress non-essential output)
- [X] T095 [P] Add `--verbose` / `-v` flag for debug output
- [X] T096 [P] Review logging: ensure no secrets logged, appropriate levels
- [X] T097 [P] Run full test suite, fix any failures
- [X] T098 [P] Create README.md with quickstart (config, first ingest, first query)
- [X] T099 Review CLI help text for all commands
- [X] T100 Final smoke test: full workflow from config → catalog ingest → deep ingest → annotations → queries → exports

**Checkpoint**: Phase 7 complete. All polish tasks completed.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 0 (Foundation)
    ↓
Phase 1 (Catalog Ingestion) ← Required for any queries
    ↓
Phase 2 (Annotations) ← Can run after Phase 1
    ↓
Phase 3 (Deep Ingestion) ← Requires Phase 1; enables roster/person queries
    ↓
Phase 4 (Drift) ← Requires Phase 3; extends ingestion
    ↓
Phase 5 (Grades) ← Requires Phase 3 (grades stored in Enrollment)
    ↓
Phase 6 (Aliasing) ← Requires Phase 1; mostly independent
    ↓
Phase 7 (Polish) ← After all phases
```

### Parallel Opportunities

Within each phase, tasks marked `[P]` can run in parallel if they touch different files.

- Phase 0: T004, T005 can run in parallel
- Phase 1: Model design (T021) blocks migration (T022); Canvas client (T023-T025) can parallel with model work
- Phase 2: Model design (T037) blocks migration (T038); annotation manager can parallel with query updates
- Phase 3: Similar pattern—models before migrations before logic

### Incremental Delivery Points

- **After Phase 0**: CLI runs, database works (no queries yet)
- **After Phase 1**: User can see their involvement timeline (MVP for Q1)
- **After Phase 2**: Declared truth operational (MVP for Q4 partial)
- **After Phase 3**: Deep queries work (MVP for Q2, Q4 complete, Q5)
- **After Phase 4**: Historical tracking works (MVP for Q6)
- **After Phase 5**: Grade summaries work (MVP for Q3)
- **After Phase 6**: Course aliasing works (MVP for Q7)

---

## Notes

- Schema decisions are made during task implementation (T021, T037, T047, T065, T084) with review before migration
- Each verification task is a gate before proceeding to next phase
- Smoke checks use real Canvas API where practical; unit tests use mocks
- Commit after each task or logical group of tasks
