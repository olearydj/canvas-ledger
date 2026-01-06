# Product Specification: canvas-ledger (cl)

**Created**: 2026-01-06
**Status**: Approved
**Version**: 1.0

## Problem Statement

Canvas LMS is effective for answering questions about the current state of a course:
who is enrolled now, what the current grades are, what content exists today. However,
Canvas is poor at answering **historical questions**:

- What courses was I involved in three years ago, and in what capacity?
- When did a student drop a course, and what was their status before dropping?
- Who was the lead instructor for a co-taught course, as opposed to the other
  instructors listed?
- How has a student's performance changed across semesters?
- When did course numbering change, and how do I view historical data coherently?

These questions matter for retrospective analysis, annual reviews, teaching
portfolios, advising, and research into teaching outcomes. Canvas does not provide
durable answers because it reflects current state, not historical record.

## Motivation

An instructor needs a **local, durable, queryable historical record** of Canvas
metadata—independent of Canvas's own retention policies, UI limitations, and
API constraints.

canvas-ledger exists to give instructors control over their own historical teaching
data, stored locally, inspectable at any time, and queryable for the kinds of
questions that Canvas cannot answer.

## Target Users

### Primary User: Instructor/Researcher

An individual instructor or researcher operating with normal Canvas permissions
(not an institution-wide admin). This user:

- Has access to courses where they hold an instructor, TA, designer, or student role
- Wants to understand their teaching history over many semesters
- Needs to answer questions about student enrollment and performance for advising,
  letters of recommendation, or research
- Values data ownership and local storage over cloud dependencies

### Secondary Use Case: Retrospective Analysis

Using accumulated ledger data to analyze patterns over time:

- Teaching load and course involvement history
- Student participation patterns across courses
- Grade distributions and outcomes at a summary level

### Non-Users

This tool is NOT designed for:

- Institution-wide administrators needing cross-instructor analytics
- Students tracking their own enrollment (though possible, not the primary focus)
- Anyone needing real-time dashboards or rich graphical interfaces

## Functional Scope

### What canvas-ledger Does

1. **Builds a local ledger of offerings**: The user can retrieve and store a list
   of all Canvas courses ("offerings") visible to them, across any role they hold.

2. **Ingests deeper data incrementally**: For selected offerings, the user can
   ingest additional data—sections, enrollments, people—without corrupting or
   duplicating existing records.

3. **Preserves change over time**: The system tracks when records were observed
   and detects changes between ingestion runs. Historical states (adds, drops,
   role changes, grade changes) can be reconstructed.

4. **Distinguishes observed vs. declared truth**:
   - **Observed truth**: Data exactly as reported by Canvas, never modified
   - **Declared truth**: User annotations that capture reality when it differs
     from Canvas (e.g., who was actually the lead instructor)

5. **Supports structured queries**: The user can query the ledger to answer
   canonical questions about courses, enrollments, people, and roles.

6. **Emits structured output**: All queries produce structured output (JSON, CSV)
   suitable for scripting, piping, and integration with other tools.

### What canvas-ledger Does NOT Do

- **Sync or manage course content**: No files, modules, pages, assignments, or
  submissions. Content authoring happens elsewhere.
- **Replace Canvas UI or gradebook**: This is a historical ledger, not a
  teaching interface.
- **Explain causal outcomes**: The system records *what* happened, not *why*.
- **Provide real-time synchronization**: Ingestion is user-initiated and
  point-in-time.
- **Provide dashboards or rich GUIs**: Output is CLI and structured data only.
- **Act as a general LMS framework**: The scope is intentionally narrow.

## User Scenarios & Acceptance Criteria

The following canonical questions define the minimum acceptance surface. Each
represents a question the system MUST be able to answer.

---

### User Story 1 - Course Involvement History (Priority: P1)

As an instructor, I want to see all courses I have been involved in at my
institution, when, and in what capacity, so that I can build a teaching portfolio
or answer questions about my history.

**Why this priority**: This is the foundational use case. Without a ledger of
offerings, nothing else is possible.

**Independent Test**: Given a configured API connection, the user can retrieve
their visible courses and see them listed with term, role, and course identifiers.

**Acceptance Scenarios**:

1. **Given** a configured Canvas API token, **When** the user requests their
   course list, **Then** all courses visible to them (any role) are retrieved
   and stored locally.

2. **Given** stored offerings, **When** the user queries their involvement,
   **Then** they see each offering with: course name, course code, term, and
   their Canvas-reported role(s).

3. **Given** a user has added a declared annotation (e.g., "lead instructor"),
   **When** they query involvement, **Then** both observed roles and declared
   annotations are shown.

---

### User Story 2 - Person Enrollment History (Priority: P1)

As an instructor, I want to see the enrollment history of a specific person
across offerings I have access to, including when they enrolled, their role,
and their enrollment lifecycle (active, dropped, concluded).

**Why this priority**: Understanding a student's trajectory is essential for
advising and letters of recommendation.

**Independent Test**: Given ingested enrollment data for multiple offerings,
a query for a specific person returns their enrollment records with lifecycle
information.

**Acceptance Scenarios**:

1. **Given** ingested enrollment data, **When** the user queries by person
   identifier, **Then** all enrollments for that person are returned with:
   offering, section, role, enrollment state, and relevant dates.

2. **Given** an enrollment that changed state (e.g., active → dropped),
   **When** the user queries that person, **Then** the historical states are
   visible, not just the final state.

---

### User Story 3 - Person Performance Summary (Priority: P2)

As an instructor, I want to see summary-level academic performance for a person
across offerings (Canvas-reported final/current grade or score).

**Why this priority**: Important for advising and retrospective analysis, but
depends on enrollment history being in place first.

**Independent Test**: Given ingested enrollment data including grades, a query
for a person returns their grade/score per offering.

**Acceptance Scenarios**:

1. **Given** ingested grade data, **When** the user queries a person's
   performance, **Then** they see each offering with the Canvas-reported
   final grade, current grade, or current score (as available).

2. **Given** grade data from multiple ingestion runs, **When** grades changed
   between runs, **Then** the system preserves both the prior and current
   values with observation timestamps.

---

### User Story 4 - Declared vs. Observed Instructors (Priority: P2)

As an instructor in a co-taught course, I want to record who was the lead or
grade-responsible instructor, so that my records reflect reality even when
Canvas lists multiple instructors without distinction.

**Why this priority**: Canvas does not distinguish lead vs. co-instructor.
This is essential for accurate teaching records.

**Independent Test**: Given an offering with multiple Canvas-reported
instructors, the user can add an annotation declaring lead responsibility,
and subsequent queries show both observed and declared data.

**Acceptance Scenarios**:

1. **Given** an offering with multiple instructors in Canvas, **When** the user
   queries instructors, **Then** all Canvas-reported instructor enrollments
   are shown.

2. **Given** the user adds a declared annotation for lead instructor, **When**
   they query the offering, **Then** both the Canvas-reported instructors and
   the declared lead are visible and clearly distinguished.

3. **Given** a declared annotation exists, **When** new ingestion runs occur,
   **Then** the annotation is preserved and Canvas-observed data is updated
   without overwriting the annotation.

---

### User Story 5 - Offering Enrollment Roster (Priority: P2)

As an instructor, I want to see who was enrolled in a specific offering,
organized by section, with their roles and enrollment states.

**Why this priority**: Foundational for understanding class composition.

**Independent Test**: Given ingested enrollment data for an offering, the user
can list all enrollments grouped by section.

**Acceptance Scenarios**:

1. **Given** ingested enrollment data, **When** the user queries an offering,
   **Then** enrollments are listed with: person identifier, section, role,
   and enrollment state.

2. **Given** an offering with multiple sections, **When** queried, **Then**
   enrollments are grouped or filterable by section.

---

### User Story 6 - Enrollment Change Over Time (Priority: P3)

As an instructor, I want to see how enrollment changed over time for a person
or offering, so I can understand adds, drops, and state transitions.

**Why this priority**: Depends on having ingestion history; valuable but not
required for initial utility.

**Independent Test**: Given multiple ingestion runs with enrollment changes,
a query shows the timeline of changes.

**Acceptance Scenarios**:

1. **Given** enrollment data ingested at multiple points in time, **When** the
   user queries enrollment history for a person, **Then** they see changes
   over time (e.g., enrolled on date X, dropped on date Y).

2. **Given** enrollment data for an offering over time, **When** queried,
   **Then** the user can see how the roster evolved (who joined, who left).

---

### User Story 7 - Course Identity and Aliasing (Priority: P3)

As an instructor, I want to associate related courses (renumbered courses,
special topics with rotating titles) so that historical queries remain coherent
across naming changes.

**Why this priority**: Important for long-term coherence but not blocking for
initial use.

**Independent Test**: Given two offerings that represent the "same" course
under different codes, the user can create an alias or grouping, and queries
can aggregate across the alias.

**Acceptance Scenarios**:

1. **Given** offerings with different course codes that represent the same
   logical course, **When** the user declares an alias or grouping, **Then**
   both offerings are associated.

2. **Given** an alias exists, **When** the user queries by alias, **Then**
   results include all associated offerings.

---

### Edge Cases

- **Deleted courses in Canvas**: If a course is deleted in Canvas but exists
  in the local ledger, the ledger preserves the record. The system does not
  delete observed data.

- **API token expiration or permission changes**: The system reports errors
  clearly when Canvas API access fails. It does not corrupt local data on
  API failure.

- **Duplicate ingestion**: Running ingestion multiple times for the same data
  does not create duplicate records. Ingestion is idempotent.

- **Missing grades**: Not all enrollments have grades. The system handles
  missing grade data gracefully without failing queries.

- **Cross-institution data**: The system assumes a single Canvas instance per
  ledger. Multi-institution support is out of scope for initial release.

## Requirements

### Functional Requirements

- **FR-001**: System MUST retrieve and store a list of all courses visible to
  the authenticated user from Canvas.

- **FR-002**: System MUST allow incremental ingestion of sections, enrollments,
  and people for selected offerings.

- **FR-003**: System MUST preserve all Canvas-observed data exactly as reported,
  with timestamps indicating when data was observed.

- **FR-004**: System MUST support user-declared annotations that coexist with
  observed data without modifying it.

- **FR-005**: System MUST detect and record changes between ingestion runs
  (drift detection).

- **FR-006**: System MUST support querying by person, offering, term, role, and
  enrollment state.

- **FR-007**: System MUST emit structured output (JSON, CSV) for all queries.

- **FR-008**: System MUST operate entirely locally with no required cloud
  services beyond the Canvas API itself.

- **FR-009**: System MUST handle API failures gracefully without corrupting
  local data.

- **FR-010**: Ingestion MUST be idempotent—repeated runs produce the same
  result without duplication.

### Key Entities

- **Offering**: A Canvas course instance—identified by Canvas course ID, with
  attributes like name, code, term, and workflow state.

- **Person**: An individual in Canvas—identified by Canvas user ID, with
  attributes like name and identifiers (SIS ID, login ID). The Canvas user ID
  is the primary stable identifier for all internal references and annotations.
  SIS ID lookup is a convenience feature but not required for core operations.

- **Enrollment**: The relationship between a person and an offering—includes
  role, section, enrollment state, grades, and lifecycle dates.

- **Section**: A subdivision of an offering—identified by Canvas section ID,
  associated with one offering.

- **Annotation**: A user-declared assertion about an entity—separate from
  observed data, timestamped, and preserved across ingestion.

- **Term**: An academic term—identified by Canvas term ID, with name and date
  range.

## Ingestion Behavior

### Conceptual Model

Ingestion is the process of retrieving data from Canvas and storing it in the
local ledger. The following principles govern ingestion:

1. **Point-in-time snapshots**: Each ingestion run captures data as of that
   moment. The system records when observations were made.

2. **Idempotent**: Running the same ingestion twice does not create duplicates.
   If data has not changed, the ledger reflects this.

3. **Drift-aware**: If data has changed since the last ingestion, the system
   records both the prior state and the new state with timestamps.

4. **Incremental**: Users can ingest data at different granularities—course
   list first, then deeper data for selected offerings—without losing or
   corrupting prior data.

5. **Non-destructive**: The system never deletes observed data, even if that
   data no longer exists in Canvas.

### Observed vs. Declared Data

- **Observed data** is immutable once recorded. New observations may be added,
  but prior observations are never modified.

- **Declared data** (annotations) is user-controlled and persists independently
  of ingestion. Annotations are never overwritten by ingestion.

## Success Criteria

### Initial Release Criteria

- **SC-001**: A user can configure Canvas API access and successfully retrieve
  their course list on first run.

- **SC-002**: A user can query their course involvement history and see all
  offerings with terms and roles.

- **SC-003**: A user can ingest enrollment data for a selected offering and
  query the roster.

- **SC-004**: A user can query a specific person's enrollment history across
  ingested offerings.

- **SC-005**: A user can add a declared annotation (e.g., lead instructor) and
  see it alongside observed data in queries.

- **SC-006**: Running ingestion twice produces no duplicates and correctly
  identifies unchanged data.

- **SC-007**: Data persists across sessions in a local database file that can
  be backed up and inspected.

- **SC-008**: All queries produce valid JSON or CSV output suitable for piping
  to other tools.

### Quality Criteria

- **QC-001**: Error messages clearly indicate the cause of failure (API error,
  missing configuration, invalid query).

- **QC-002**: The local database is a single portable file with no external
  service dependencies.

- **QC-003**: Ingestion handles large course lists (100+ offerings) without
  failure or unreasonable delay.

- **QC-004**: Deep ingestion handles offerings with 1000+ enrollments without
  failure or unreasonable delay.

## Appendix: Canonical Questions Mapping

| Canonical Question | Supported By |
|--------------------|--------------|
| What courses have I been involved in, when, and in what capacity? | User Story 1 |
| For a given person, what offerings were they enrolled in? | User Story 2 |
| For a given person, how did they perform at a summary level? | User Story 3 |
| Who was the declared lead instructor vs. Canvas-reported? | User Story 4 |
| Who was enrolled in an offering, by section and role? | User Story 5 |
| How did enrollment change over time? | User Story 6 |
| How to handle course renumbering and aliasing? | User Story 7 |
