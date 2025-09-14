# Email Behavior Orchestrator

## Overview

The Email Behavior Orchestrator is a Streamlit application designed to assist email teams in managing incoming emails more efficiently. By leveraging AI for intent recognition, the application proposes actions based on predefined rules while keeping human decision-makers in control.

## Project Structure

```
finkraft-t13
├── src
│   ├── app.py                # Entry point for the Streamlit application
│   ├── core
│   │   ├── orchestrator.py    # Main logic for handling email threads
│   │   ├── rules.py           # Action rules for determining responses
│   │   └── logger.py          # Logging configuration for debugging
│   ├── ai
│   │   ├── integrations.py     # AI integration for intent recognition
│   │   └── schemas.py         # Data schemas for validation
│   ├── db
│   │   ├── models.py          # Database models using SQLAlchemy
│   │   ├── crud.py            # CRUD operations for database interactions
│   │   └── session.py         # Database session management
│   ├── config
│   │   └── settings.py        # Configuration settings for the application
│   └── utils
│       └── persistence.py      # Data persistence utilities
├── data
│   └── sample_threads.json     # Sample email threads for testing
├── tests
│   └── test_orchestrator.py    # Unit tests for the orchestrator logic
├── Pipfile                     # Project dependencies
├── .gitignore                  # Files to ignore in Git
└── README.md                   # Project documentation
```

## Setup Instructions

1. **Clone the Repository**:

   ```bash
   git clone <repository-url>
   ```

2. **Create a Virtual Environment**:
   ```bash
   pipenv shell
   ```

# Email Behavior Orchestrator

A Streamlit app that helps email teams manage incoming threads by proposing AI-suggested actions while keeping humans as the decision-makers.

## Features

- Upload JSON email threads and persist threads/messages in a local SQLite DB.
- AI intent detection and suggested actions persisted as `AISuggestion` records.
- Provenance: raw AI responses are serialized and stored in `ai_suggestions.raw_response` and exposed in the UI.
- Human control: Accept/Override UI records decisions in `user_decisions` and generates editable drafts.
- Draft lifecycle: Drafts persisted in `email_drafts` and can be marked as `sent` (DB-only by default).

## Quickstart

1. Install dependencies and enter the virtualenv (this project uses Pipfile/Pipenv):

```bash
pipenv install
pipenv shell
```

2. (Optional) Run the lightweight migration helper to ensure schema is current:

```bash
python -c "from db.session import ensure_db_schema; ensure_db_schema(); print('migration ran')"
```

3. Run the Streamlit app:

```bash
streamlit run finkraft-t13/src/app.py
```

## High-level Flow

1. Upload a JSON file containing threads (either a list of thread objects, or `{ "threads": [...] }`).
2. The app persists the thread and messages and calls the AI wrapper to produce an `AISuggestion`.
3. The suggestion (intent, confidence, suggested_action, required fields, follow-up) is stored and shown in the UI.
4. The user may `Accept` or `Override` the suggestion. Accept creates an editable draft persisted in `email_drafts`.
5. The user edits the draft and clicks `Send` — currently this marks the draft as `sent` in the DB and records `sent_at`.

## Developer Notes

- Important files:

  - `src/app.py` — Streamlit UI and flows
  - `src/core/orchestrator.py` — upload processing and AI integration
  - `src/ai/integrations.py` — AI wrapper and schema models
  - `src/db/models.py` & `src/db/crud.py` — SQLAlchemy models and CRUD helpers
  - `src/db/session.py` — DB session and lightweight migration helper

- Lightweight migration: `ensure_db_schema()` in `src/db/session.py` will create tables and add the `raw_response` column on SQLite if missing. For any production work, use Alembic instead.

- Sending email: There is no SMTP/provider integration yet. `mark_draft_sent` flips `status` to `sent` and sets `sent_at` — this can be replaced by a real sender module.

## Limitations & Next Steps

- email inbound can be automated via an email provider webhook or IMAP polling.
- No external email delivery (SMTP/API) integrated — implement a `sender` module and wire it into the `Send` action.
- Add user authentication, roles and permissions for multi-user scenarios.
- Add async workers to handle AI calls and email sending outside the request cycle.

## Quick Debug / Re-run Steps

- Recreate DB and run lightweight migration (helpful after schema changes):

```bash
python -c "from db.session import ensure_db_schema; ensure_db_schema(); print('migration ran')"
streamlit run finkraft-t13/src/app.py
```

## Author Background

- The author has limited experience with Streamlit and frontend/UI development. The interface is intentionally simple and focuses on demonstrating the backend orchestration, persistence, and AI integration.
- Primary expertise: console applications and REST API development. Please treat the visual/UX aspects of the UI as a minimal demo rather than a polished production UI.
