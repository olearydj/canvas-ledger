<!--
  ============================================================================
  SYNC IMPACT REPORT
  ============================================================================
  Version Change: N/A → 1.0.0 (Initial ratification)

  Added Principles:
    - I. Metadata, Not Content
    - II. Canvas as Observed Truth; Annotations as Declared Truth
    - III. Historical Accuracy Over Convenience
    - IV. Local, Inspectable, and Durable
    - V. CLI-First, Composable Design
    - VI. Loose Coupling with Downstream Tools
    - VII. Schema Evolution Is Expected
    - VIII. Minimal Surface Area, Deliberate Growth
    - IX. Instructor-Centric, Not Admin-Centric
    - X. Correctness Beats Cleverness

  Added Sections:
    - Non-Goals
    - Decision Rule
    - Tooling and Workflow Constraints
    - Governance

  Removed Sections: None (initial creation)

  Templates Consistency:
    ✅ .specify/templates/plan-template.md - "Constitution Check" section exists,
       will reference principles dynamically
    ✅ .specify/templates/spec-template.md - No constitution-specific updates needed
    ✅ .specify/templates/tasks-template.md - No constitution-specific updates needed
    ✅ No command files found to update

  Deferred TODOs: None
  ============================================================================
-->

# canvas-ledger Constitution

## Purpose

canvas-ledger (cl) is a local, instructor-owned CLI tool for maintaining a queryable
ledger of Canvas LMS metadata. The goal is to answer historically meaningful questions
about course involvement, roles, enrollments, and outcomes that are difficult or
impossible to answer in Canvas itself.

## Core Principles

### I. Metadata, Not Content

The system ingests and models Canvas metadata only (courses, roles, enrollments,
grades at a summary level). It explicitly does NOT sync or manage course content
(files, modules, pages, assignments).

**Rationale**: Content management is out of scope. Keeping the scope narrow ensures
the tool remains maintainable and focused on its core purpose: historical record
keeping of metadata.

### II. Canvas as Observed Truth; Annotations as Declared Truth

What Canvas reports MUST always be preserved as observed data. When reality differs
(e.g., lead instructor vs co-instructor), corrections MUST be stored as explicit,
user-declared annotations—never inferred or overwritten.

**Rationale**: Canvas data is authoritative for what it reports. Human corrections
are separately tracked to maintain auditability and avoid data loss.

### III. Historical Accuracy Over Convenience

The system MUST preserve time, drift, and change (adds/drops, role changes).
Idempotent ingestion and change awareness matter more than minimizing storage
or simplifying the model.

**Rationale**: The primary value of this tool is answering historical questions.
Sacrificing historical fidelity for convenience would undermine the core purpose.

### IV. Local, Inspectable, and Durable

The primary artifact is a local SQLite database. It MUST be easy to inspect,
back up, migrate, and reason about. No hidden services, no required cloud components.

**Rationale**: Instructors need full control over their data. Local-first design
ensures portability, privacy, and independence from external services.

### V. CLI-First, Composable Design

All functionality MUST be exposed via a CLI. Commands MUST be scriptable and
composable (Unix-style). The tool MUST emit structured outputs (JSON/CSV) suitable
for piping into other tools.

**Rationale**: CLI-first design enables automation, integration with existing
workflows, and long-term maintainability without UI dependencies.

### VI. Loose Coupling with Downstream Tools

Other tools MAY consume data from cl, but only through explicit exports or imports.
No shared databases, no tight runtime integration, no assumption that other tools
know cl's internal schema.

**Rationale**: Loose coupling preserves freedom to evolve the schema and
architecture without breaking external consumers.

### VII. Schema Evolution Is Expected

The database schema will change over time. Migrations MUST be first-class,
forward-only, and explicit. External consumers MUST rely on exported artifacts,
not internal tables.

**Rationale**: Accepting that schema will evolve prevents premature optimization
and allows the model to grow with real needs.

### VIII. Minimal Surface Area, Deliberate Growth

The system MUST start small and grow only to support clearly articulated canonical
queries. Avoid speculative features, generic LMS abstractions, or enterprise patterns.

**Rationale**: Feature creep is the enemy of useful tools. Every addition must
justify its existence against a real, documented need.

### IX. Instructor-Centric, Not Admin-Centric

The primary user is an instructor/researcher operating with normal Canvas permissions.
The design MUST NOT assume institution-wide admin access.

**Rationale**: Most instructors do not have admin privileges. Designing for the
common case ensures broad utility.

### X. Correctness Beats Cleverness

Prefer clear, explicit logic over inference, heuristics, or "smart" guesses—
especially around roles, responsibility, and course identity.

**Rationale**: In record-keeping systems, incorrect inferences cause lasting harm.
Explicit logic is debuggable and auditable.

## Non-Goals

The following are explicitly out of scope:

- Replacing Canvas UI or gradebook
- Explaining causal outcomes (e.g., why a student received a grade)
- Real-time synchronization
- Dashboards or rich GUIs
- Acting as a general LMS framework

## Decision Rule

When in doubt, choose the option that:

1. Preserves history
2. Makes fewer assumptions
3. Keeps the system simpler to reason about
4. Keeps canvas-ledger a trustworthy source of record for Canvas metadata

## Tooling and Workflow Constraints

- Use `uv` for Python environment and dependency management
- Avoid direct use of `pip` or alternative dependency managers
- Prefer explicit, inspectable tooling over "magic" abstractions
- Favor simple, durable choices over trendy or experimental tooling unless
  there is clear justification

## Governance

### Amendment Procedure

1. Proposed amendments MUST be documented with rationale
2. Changes to principles require review against existing features for impact
3. All amendments MUST include migration guidance if they affect existing code
4. Version number MUST be updated according to semantic versioning rules

### Versioning Policy

- **MAJOR**: Backward-incompatible principle removals or redefinitions
- **MINOR**: New principle/section added or materially expanded guidance
- **PATCH**: Clarifications, wording, typo fixes, non-semantic refinements

### Compliance Review

- All PRs MUST be reviewed for compliance with these principles
- The Constitution supersedes convenience—complexity MUST be justified
- When principles conflict, apply the Decision Rule above

**Version**: 1.0.0 | **Ratified**: 2026-01-06 | **Last Amended**: 2026-01-06
