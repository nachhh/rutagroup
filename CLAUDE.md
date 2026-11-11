# CLAUDE.md: working agreement for this repo

Ruta Group is a learning playground for a Unified Data Layer, a semantic layer, governance-as-code,
and BigQuery + Redshift(-as-Postgres). The roadmap is in [README.md](README.md). Per-phase
specs are in [specs/](specs/).

## Workflow rules (persist across sessions)

1. **Spec-driven.** Each phase has `specs/phase-<n>-<title>.md`, the source of truth for
   that phase: goals, files to create, table schemas, YAML layout, acceptance criteria. Update the
   spec *before* changing scope. README keeps only the summary and the progress tracker.
2. **Phase intro in chat first.** Before starting any phase, give a short chat intro to the key
   technical terms of that phase, especially the user's weak points (semantic layers, UDL/context
   layers, ontologies/KGs, dbt SL/MetricFlow, NL querying, BQ+Redshift, governance). Do this even if
   the terms are also in `docs/glossary.md`.
3. **Decision checkpoints (🧭).** Stop and ask the user. Don't decide silently.
4. **Quizzes (🧠).** Ask in chat one question at a time. The user answers before seeing the solution.
   Once a quiz is settled, write it (questions, user's answers, feedback) to
   `quizzes/quiz-<n>-<title>.md`. `quizzes/` is gitignored.
5. **Git: always ask first** before any commit, branch, merge, push, or tag. Suggested cadence:
   one commit per phase.
6. **Public repo hygiene.** Never commit secrets, keys, `profiles.yml`, `.env`, the job posting,
   `CLAUDE.local.md`, or `quizzes/`. Check `git status` before proposing a commit. Keep committed
   text neutral: no references to a specific employer or interview.
7. **Glossary.** Every new technical term goes into `docs/glossary.md` as EN ↔ ES with a
   one-line definition.
8. **Diagrams.** Mermaid diagrams live in `docs/diagrams/*.md` (the user previews them with
   Markdown Preview Mermaid). Update them when the model changes.
9. **The agent (Phase 6) is KIS.** Document it in code comments only: no extra docs, no quiz.

## Stack conventions

- Python 3.12 via `uv` (system Python is 3.14, which dbt doesn't support well). Airflow lives in a
  separate venv to avoid dependency conflicts with dbt.
- Postgres 16 in Docker plays **Redshift** (RutaShip). The **BigQuery Sandbox** hosts RutaPay
  and the UDL. Sandbox limits: no DML (`INSERT/UPDATE/MERGE`), so no incremental MERGE or
  snapshots on BQ; tables expire after 60 days; no GCS without billing.
- BQ auth uses gcloud ADC (`gcloud auth application-default login`), never a key file in the repo.
- Use BigQuery-native SQL generously in BQ models (STRUCT/ARRAY, UNNEST, JSON functions,
  QUALIFY, SAFE_*, GENERATE_DATE_ARRAY, EDIT_DISTANCE, partition/cluster configs) and comment
  *why* each one is used.
